"""Activity: one A2A 1.0 message to a prokube Agent through the AI Gateway.

The reply stream is read inside the activity with heartbeats, the message id
comes from the workflow, and A2A error replies are not retried. A task that
waits for a tool approval is returned as such; the workflow answers it with a
second call.

In a notebook, A2A_URL is https://<domain>/svc/a2a/<workspace> and A2A_API_KEY
a prokube API key with access to the Agents. A worker deployed in the
workspace uses the gateway inside the cluster with its own token instead.
"""

import json
import os
from dataclasses import dataclass, field

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

HITL = "https://kagent.dev/extensions/hitl/v1"
GATEWAY = "http://agentgateway-proxy.agentgateway-system.svc.cluster.local"


def _endpoint() -> tuple[str, str]:
    """A2A base URL and bearer token."""
    if os.environ.get("A2A_API_KEY"):
        return os.environ["A2A_URL"], os.environ["A2A_API_KEY"]
    from prokube.workflows import worker_token  # pylint: disable=import-outside-toplevel

    return f"{GATEWAY}/usr/a2a/{os.environ['TEMPORAL_NAMESPACE']}", worker_token()


@dataclass
class ToolApproval:
    id: str
    name: str
    args: dict


@dataclass
class A2AMessage:
    agent: str
    message_id: str
    text: str = ""
    # Answer a task that waits for tool approvals instead of sending text.
    task_id: str = ""
    context_id: str = ""
    approvals: dict[str, bool] = field(default_factory=dict)


@dataclass
class A2AResult:
    state: str
    text: str
    task_id: str = ""
    context_id: str = ""
    tool_approvals: list[ToolApproval] = field(default_factory=list)


def _parts_text(parts) -> str:
    return "".join(p.get("text", "") for p in parts or [] if isinstance(p, dict))


def _message(msg: A2AMessage) -> dict:
    message = {"messageId": msg.message_id, "role": "ROLE_USER"}
    if not msg.task_id:
        return {**message, "parts": [{"text": msg.text}]}
    return {
        **message,
        "taskId": msg.task_id,
        "contextId": msg.context_id,
        "parts": [{"text": "approved" if all(msg.approvals.values()) else "rejected"}],
        "extensions": [HITL],
        "metadata": {HITL: {
            "type": "tool_approval_response",
            "approvals": [{"id": i, "approved": ok} for i, ok in msg.approvals.items()],
        }},
    }


@activity.defn
async def send_a2a_message(msg: A2AMessage) -> A2AResult:
    base, token = _endpoint()
    url = f"{base}/{msg.agent}"
    body = {"jsonrpc": "2.0", "id": msg.message_id, "method": "SendStreamingMessage",
            "params": {"message": _message(msg)}}
    artifacts: dict[str, str] = {}
    state, task_id, context_id, status = "", "", "", {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10, read=120)) as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "A2A-Version": "1.0",
            "A2A-Extensions": HITL,
            "Accept": "text/event-stream",
        }
        async with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code in (401, 403, 404):
                raise ApplicationError(f"{msg.agent}: HTTP {response.status_code}", non_retryable=True)
            response.raise_for_status()
            async for line in response.aiter_lines():
                activity.heartbeat()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if "error" in event:
                    raise ApplicationError(f"{msg.agent}: {event['error']}", non_retryable=True)
                result = event.get("result") or {}
                holder = result.get("task") or result.get("statusUpdate") or {}
                task_id = holder.get("id") or holder.get("taskId") or task_id
                context_id = holder.get("contextId") or context_id
                if holder.get("status"):
                    status = holder["status"]
                    state = status.get("state", state)
                if "artifactUpdate" in result:
                    update = result["artifactUpdate"]
                    artifact = update.get("artifact") or {}
                    key = artifact.get("artifactId", "")
                    chunk = _parts_text(artifact.get("parts"))
                    artifacts[key] = artifacts.get(key, "") + chunk if update.get("append") else chunk
                if "message" in result:
                    artifacts["message"] = _parts_text(result["message"].get("parts"))
    hitl = ((status.get("message") or {}).get("metadata") or {}).get(HITL) or {}
    tools = (hitl.get("nested") or {}).get("tools") or hitl.get("tools") or []
    hint = hitl.get("hint", "")
    text = "\n".join(t for t in artifacts.values() if t and t not in hint).strip()
    return A2AResult(
        state=state.removeprefix("TASK_STATE_").lower(),
        text=text,
        task_id=task_id,
        context_id=context_id,
        tool_approvals=[ToolApproval(t["id"], t.get("name", ""), t.get("args") or {}) for t in tools],
    )
