# An agent workflow with an approval

A [Temporal](https://temporal.io/) workflow asks a prokube Agent over A2A to
research a topic, waits until a person approves the result, then asks the
Agent for a summary. Tool calls the Agent wants to make become approvals of
the run as well.

## Prerequisites

- Workflows (Temporal) enabled on your prokube cluster.
- An Agent in your workspace; the notebook uses `research-assistant`.
- A prokube API key with access to the Agent: in the prokube UI under
  **AI Gateway**, **API keys**.

## How it works

- [`workflows.py`](./workflows.py) is the workflow. It waits for approvals
  the way Temporal recommends: `wait_condition`, the decision as an Update
  with a validator, the open question as a Query, and the Search Attribute
  `ApprovalStatus=Pending`, which the prokube UI lists under **Waiting for
  approval**.
- [`activities.py`](./activities.py) sends one A2A 1.0 message to the Agent
  through the AI Gateway (`https://<domain>/svc/a2a/<workspace>/<agent>`) and
  reads the reply stream.
- The notebook logs you in to Temporal, runs a worker in the background,
  starts a run and lets you answer the approvals. The run also shows under
  **Workflows** in the prokube UI, where you can answer them instead.

## Run the notebook

Open [`agent-approval.ipynb`](./agent-approval.ipynb) in a prokube Lab, set
your platform URL and run the cells. The login prints a URL and a code: open
the URL in your browser and confirm the code.
