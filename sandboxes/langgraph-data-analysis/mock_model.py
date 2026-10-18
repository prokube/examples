"""A stand-in for a real model, so the notebook runs without one.

It makes the tool calls in SCRIPT in order, then answers with the last line
of the first one's output.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ANALYSIS = """\
import matplotlib
matplotlib.use("Agg")
import pandas as pd

revenue = pd.read_csv("sales.csv").pivot_table(index="month", columns="region", values="revenue")
growth = (revenue.iloc[-1] / revenue.iloc[0] - 1).sort_values()
print(f"{growth.index[-1]} grew fastest: {growth.iloc[-1]:+.0%} from January to December.")
revenue.plot(title="Monthly revenue per region").figure.savefig("revenue.png")
"""

SCRIPT = [
    ("run_python", {"code": ANALYSIS}),
    ("show_image", {"path": "/workspace/revenue.png"}),
]


class ScriptedModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        question = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        results = [m for m in messages[question:] if isinstance(m, ToolMessage)]
        if len(results) < len(SCRIPT):
            name, args = SCRIPT[len(results)]
            call = {"name": name, "args": args, "id": f"call-{len(messages)}"}
            reply = AIMessage("", tool_calls=[call])
        else:
            reply = AIMessage(results[0].content.splitlines()[-1])
        return ChatResult(generations=[ChatGeneration(message=reply)])
