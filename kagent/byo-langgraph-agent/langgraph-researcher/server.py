import json
import logging
from pathlib import Path

import uvicorn
from agent import graph
from kagent.core import KAgentConfig
from kagent.langgraph import KAgentApp

logging.basicConfig(level=logging.INFO)

agent_card = json.loads(
    Path(__file__).with_name("agent-card.json").read_text(encoding="utf-8")
)
app = KAgentApp(
    graph=graph,
    agent_card=agent_card,
    config=KAgentConfig(),
    tracing=False,
).build()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
