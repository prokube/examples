"""A fixed LangGraph workflow: find the URL, fetch the page, summarize it."""

import json
import re

import httpx
from bs4 import BeautifulSoup
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph

URL_PATTERN = re.compile(r"https://[^\s\"'<>]+")


class State(MessagesState):
    url: str
    page_text: str
    error: str


def chat_model(config_path: str = "/config/config.json") -> BaseChatModel:
    """Build the chat model from the ModelConfig the platform passes in."""
    with open(config_path, encoding="utf-8") as file:
        model = json.load(file)["agent"]["model"]
    headers = model.get("headers") or None
    if "anthropic" in model:
        return ChatAnthropic(
            model=model["model"],
            base_url=model["anthropic"].get("base_url") or None,
            default_headers=headers,
            max_tokens=300,
        )
    return ChatOpenAI(
        model=model["model"],
        base_url=model.get("openai", {}).get("base_url") or None,
        default_headers=headers,
        max_tokens=300,
    )


def find_url(state: State) -> dict:
    match = URL_PATTERN.search(str(state["messages"][-1].content))
    if not match:
        return {"error": "Include an https:// URL in your request."}
    return {"url": match.group(0).rstrip(".,;:!?)]"), "error": ""}


def fetch_page(state: State) -> dict:
    try:
        response = httpx.get(state["url"], timeout=20, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as error:
        return {"error": f"Could not fetch {state['url']}: {error}"}
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return {"page_text": " ".join(soup.get_text(" ").split())[:8000]}


def summarize(state: State) -> dict:
    response = chat_model().invoke(
        [
            SystemMessage(
                "Summarize the web page in one sentence, using only its content."
            ),
            HumanMessage(f"URL: {state['url']}\n\n{state['page_text']}"),
        ]
    )
    return {"messages": [AIMessage(f"{response.text}\n\nSource: {state['url']}")]}


def report_error(state: State) -> dict:
    return {"messages": [AIMessage(state["error"])]}


def next_step(step: str):
    return lambda state: "report_error" if state.get("error") else step


builder = StateGraph(State)
builder.add_node(find_url)
builder.add_node(fetch_page)
builder.add_node(summarize)
builder.add_node(report_error)
builder.add_edge(START, "find_url")
builder.add_conditional_edges("find_url", next_step("fetch_page"))
builder.add_conditional_edges("fetch_page", next_step("summarize"))
builder.add_edge("summarize", END)
builder.add_edge("report_error", END)
graph = builder.compile()
