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
endpoint with tool calling, for example a model from [LLM Serving](/pkui/llm).
Without one, the notebook uses [`mock_model.py`](./mock_model.py), a stand-in
that makes fixed tool calls.

## How it works

- The tools `run_python` and `show_image` are one SDK call each. Since they
  are plain functions, other agent frameworks can use them too.
- One sandbox per conversation. The notebook creates it from the platform's
  default preset, installs pandas and matplotlib into `/workspace` and uploads
  [`sales.csv`](./sales.csv). It resumes the sandbox before each question and
  suspends it after each answer. `/workspace` survives, so the packages, the
  data and the agent's files are there for the next question.
- The agent runs in the notebook. Only the code it writes runs in the sandbox,
  isolated from the Lab, with the preset's network rules.

## Run the notebook

Open [`langgraph-data-analysis.ipynb`](./langgraph-data-analysis.ipynb) in a
prokube Lab and run its cells. To run it on a laptop, log in first as
described in the [sandbox examples](../README.md).

## Clean up

The notebook's last cell deletes the sandbox. If the notebook stopped before
it, run that cell.
