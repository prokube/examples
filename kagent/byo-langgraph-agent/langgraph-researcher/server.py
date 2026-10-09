import json
import logging
from pathlib import Path

import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import AgentCard
from agent import graph
from fastapi import FastAPI, Request
from kagent.core import KAgentConfig
from kagent.core.a2a import (
    KAgentRequestContextBuilder,
    KAgentTaskStore,
    get_a2a_max_content_length,
    get_request_user_id,
    set_request_user_id,
)
from kagent.langgraph import LangGraphAgentExecutor

logging.basicConfig(level=logging.INFO)

agent_card = AgentCard.model_validate_json(
    Path(__file__).with_name("agent-card.json").read_text(encoding="utf-8")
)
config = KAgentConfig()


async def _forward_user_id(request: httpx.Request) -> None:
    if user_id := get_request_user_id():
        request.headers["X-User-Id"] = user_id


# KAgentApp.build() saves tasks without the caller's identity, so kagent files
# them under its fallback user and they are missing from the user's chat
# history. Build the same app with a task store client that forwards the
# caller. See https://github.com/kagent-dev/kagent/issues/3052.
task_store = KAgentTaskStore(
    httpx.AsyncClient(base_url=config.url, event_hooks={"request": [_forward_user_id]})
)
request_handler = DefaultRequestHandler(
    agent_executor=LangGraphAgentExecutor(graph=graph, app_name=config.app_name),
    task_store=task_store,
    request_context_builder=KAgentRequestContextBuilder(task_store=task_store),
)

app = FastAPI(title=agent_card.name, description=agent_card.description)


@app.middleware("http")
async def _set_user_id(request: Request, call_next):
    # The A2A handler reads existing tasks before its context builder sets the
    # caller, so set it from the forwarded header first.
    set_request_user_id(request.headers.get("x-user-id"))
    return await call_next(request)


A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
    max_content_length=get_a2a_max_content_length(),
).add_routes_to_app(app)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
