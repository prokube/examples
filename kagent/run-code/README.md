# Let an agent run code

Agents have no shell of their own. To compute, transform data or install
packages, an agent starts a sandbox and runs code there. This example creates
`analyst`, an agent that answers questions with Python. It uses the model
configuration from [`basic-agent`](../basic-agent/).

## How it works

- [`sandbox-template.yaml`](./sandbox-template.yaml) is the environment the
  code runs in: a pinned Python image on the platform's shared workers. It
  lists no network destinations, so the code has no internet access.
- [`template.yaml`](./template.yaml) gives the agent the sandbox tools from
  the `kagent-api` tool server and tells it which sandbox template to use.
- [`agent.yaml`](./agent.yaml) runs the template on the `default` harness.

Each sandbox is its own isolated environment with a time limit. It cannot
reach the agent or the platform's management APIs.

In the UI, the same agent is one switch: **Run code** under
**Capabilities** when creating an agent.

## Deploy

The sandbox tools come from the `kagent-api` tool server. If no agent in the
workspace uses **Run code** yet, enable it once on any agent, or create the
server under **Tools**.

```bash
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f sandbox-template.yaml -f agent.yaml
kubectl wait --for=condition=Ready sandboxtemplate.api.kagent.dev/analyst-code agent.api.kagent.dev/analyst --timeout=5m
```

## Try it

Open `analyst` on the **Agents** page and ask:

```text
What is the sum of all primes below one million?
```

The chat shows the agent creating a sandbox, running a script and deleting
the sandbox again. The answer is 37550402023. While it runs, the sandbox is
listed on the **Sandboxes** page under **Agent sandboxes**.

Asking it to `pip install` a package fails: the sandbox has no network yet.
[`allowed-hosts`](../allowed-hosts/) changes that.

## Clean up

Skip this if you continue with [`allowed-hosts`](../allowed-hosts/).

```bash
kubectl delete -f agent.yaml -f template.yaml -f sandbox-template.yaml
```
