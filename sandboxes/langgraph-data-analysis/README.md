# Data analysis agent with sandbox tools

This example builds a
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) agent
that analyses a CSV file in a prokube sandbox and shows a chart. The agent's
tools are plain functions around the prokube SDK, and the notebook, not the
framework, owns the sandbox.

## Prerequisites

Sandboxes must be enabled on your prokube cluster, and the Lab needs sandbox
access: when you create it, enable **Allow access to sandboxes** under
**Configurations**. For a real agent you need an OpenAI-compatible model
endpoint with tool calling, for example a model from [LLM Serving](/pkui/llm)
or an external provider. Without one, the notebook uses
[`mock_model.py`](./mock_model.py), a stand-in that makes fixed tool calls.

## How it works

- The tools `run_python`, `write_file`, `read_file` and `show_image` are one
  SDK call each:

  ```python
  def run_python(code: str) -> str:
      """Run a Python script in the sandbox, in /workspace. pandas and matplotlib are installed."""
      result = sandboxes.run(SANDBOX, "/workspace/venv/bin/python -", stdin=code, cwd="/workspace")
      return f"exit code {result.exit_code}\n{result.stdout}{result.stderr}"
  ```

- One sandbox per conversation. The notebook creates it from the platform's
  default preset, installs pandas and matplotlib into `/workspace` and uploads
  [`sales.csv`](./sales.csv). It resumes the sandbox before each question and
  suspends it after each answer. `/workspace` survives, so the packages, the
  data and the agent's files are there for the next question.
- The agent runs in the notebook. Only the code it writes runs in the sandbox,
  isolated from the Lab, with the preset's network rules.

## Run the notebook

Open [`langgraph-data-analysis.ipynb`](./langgraph-data-analysis.ipynb) in a
prokube Lab and run its cells.

## Run it on a laptop

Log in once; `SandboxClient()` then uses your login and workspace instead of
the Lab's:

```bash
pip install 'prokube-sdk[cli] @ git+https://github.com/prokube/prokube-sdk@sandboxv3/main'
pk login https://<your-prokube-domain> --workspace <workspace>
```

Then run the notebook in your local Jupyter.

## Use the tools in another framework

The tool functions do not depend on LangGraph. With
[Pydantic AI](https://ai.pydantic.dev/), which reads `OPENAI_BASE_URL` and
`OPENAI_API_KEY` from the environment:

```python
from pydantic_ai import Agent

agent = Agent(
    "openai:<model>",
    tools=[run_python, write_file, read_file, show_image],
    system_prompt="You are a data analyst. Use the tools to work in the sandbox.",
)
print(agent.run_sync("Which region grew fastest in /workspace/sales.csv?").output)
```

## Clean up

The notebook's last cell deletes the sandbox. If the notebook stopped before
it, run that cell.
