import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

ALLOWED_HOSTS = {"prokube.ai", "www.prokube.ai"}
URL_PATTERN = re.compile(r"https://[^\s]+")


class WorkflowState(MessagesState):
    url: str
    page_text: str
    draft: str
    error: str
    summary_valid: bool


def _extract_allowed_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None

    url = match.group(0).rstrip('.,;:!?)"]')
    if not _is_allowed_url(url):
        return None
    return url


def _is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    try:
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _message_text(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )


def _model() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        temperature=0,
        max_tokens=300,
    )


def validate_request(state: WorkflowState) -> dict[str, str]:
    message = state["messages"][-1]
    prompt = _message_text(message.content)
    url = _extract_allowed_url(prompt)
    if not url:
        return {
            "error": "Include an https://prokube.ai URL in your request.",
            "url": "",
        }
    return {"error": "", "url": url}


def fetch_page(state: WorkflowState) -> dict[str, str]:
    try:
        url = state["url"]
        with httpx.Client(
            timeout=20,
            headers={"User-Agent": "prokube-langgraph-example/1.0"},
        ) as client:
            for _ in range(6):
                response = client.get(url, follow_redirects=False)
                if not response.is_redirect:
                    response.raise_for_status()
                    break

                location = response.headers.get("location")
                next_url = urljoin(url, location) if location else ""
                if not _is_allowed_url(next_url):
                    return {"error": "The page redirected to an unsupported URL."}
                url = next_url
            else:
                return {"error": "The page redirected too many times."}
    except (httpx.HTTPError, ValueError):
        return {"error": "The page could not be fetched."}

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    page_text = " ".join(soup.get_text(" ", strip=True).split())[:8_000]
    if not page_text:
        return {"error": "The page did not contain readable text."}
    return {"error": "", "page_text": page_text}


def summarize_page(state: WorkflowState) -> dict[str, str]:
    response = _model().invoke(
        [
            SystemMessage(
                content=(
                    "Summarize the supplied website in one concise sentence. "
                    "End with 'Source: <url>'. Use only the supplied content."
                )
            ),
            HumanMessage(
                content=f"URL: {state['url']}\n\nContent:\n{state['page_text']}"
            ),
        ]
    )
    return {"draft": _message_text(response.content)}


def verify_summary(state: WorkflowState) -> dict[str, bool]:
    draft = state["draft"].strip()
    return {
        "summary_valid": 40 <= len(draft) <= 700 and state["url"] in draft,
    }


def revise_summary(state: WorkflowState) -> dict[str, str]:
    response = _model().invoke(
        [
            SystemMessage(
                content=(
                    "Rewrite the draft as one concise sentence followed by "
                    "'Source: <url>'. Preserve only claims supported by the draft."
                )
            ),
            HumanMessage(content=f"URL: {state['url']}\n\nDraft:\n{state['draft']}"),
        ]
    )
    return {"draft": _message_text(response.content)}


def finish(state: WorkflowState) -> dict[str, list[AIMessage]]:
    if state.get("error"):
        return {"messages": [AIMessage(content=state["error"])]}

    result = state["draft"].strip()
    if state["url"] not in result:
        result = f"{result}\n\nSource: {state['url']}"
    return {"messages": [AIMessage(content=result)]}


def route_after_validation(state: WorkflowState) -> str:
    return "finish" if state.get("error") else "fetch_page"


def route_after_fetch(state: WorkflowState) -> str:
    return "finish" if state.get("error") else "summarize_page"


def route_after_verification(state: WorkflowState) -> str:
    return "finish" if state["summary_valid"] else "revise_summary"


builder = StateGraph(WorkflowState)
builder.add_node("validate_request", validate_request)
builder.add_node("fetch_page", fetch_page)
builder.add_node("summarize_page", summarize_page)
builder.add_node("verify_summary", verify_summary)
builder.add_node("revise_summary", revise_summary)
builder.add_node("finish", finish)

builder.add_edge(START, "validate_request")
builder.add_conditional_edges("validate_request", route_after_validation)
builder.add_conditional_edges("fetch_page", route_after_fetch)
builder.add_edge("summarize_page", "verify_summary")
builder.add_conditional_edges("verify_summary", route_after_verification)
builder.add_edge("revise_summary", "finish")
builder.add_edge("finish", END)

graph = builder.compile()
