"""A stand-in for a real model, so the notebook runs without one.

It makes the tool calls of its script in order, then answers with the output
of the `run` call.
"""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

PRIMES = """\
def primes_below(n):
    return [p for p in range(2, n) if all(p % d for d in range(2, int(p**0.5) + 1))]

assert primes_below(10) == [2, 3, 5, 7]
print(primes_below(50))
"""

SCRIPT = [
    ("create", {"name": "mcp-demo"}),
    (
        "write_file",
        {"name": "mcp-demo", "path": "/workspace/primes.py", "content": PRIMES},
    ),
    ("run", {"name": "mcp-demo", "command": "python3 /workspace/primes.py"}),
    ("delete", {"name": "mcp-demo"}),
]


def _next_step(messages, info: AgentInfo) -> ModelResponse:
    results = [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    if len(results) == len(SCRIPT):
        return ModelResponse(
            parts=[TextPart(f"The primes below 50: {results[2].content['stdout']}")]
        )
    name, args = SCRIPT[len(results)]
    # Agent Gateway prefixes the tool names when the workspace has several MCP servers.
    tool = next(
        t.name
        for t in info.function_tools
        if t.name in (name, f"sandbox-example_{name}")
    )
    return ModelResponse(parts=[ToolCallPart(tool, args)])


scripted_model = FunctionModel(_next_step)
