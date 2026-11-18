# Delegate to another agent

This example lets a coordinator hand web research to `web-researcher` from
[`agent-with-mcp`](../agent-with-mcp/).

## How it works

[`template.yaml`](./template.yaml) binds the researcher's template as a
sub-agent:

```yaml
tools:
- subAgent:
    name: web_researcher
    description: Researches information on the web and cites the source URL
    templateRef:
      name: web-researcher
```

The coordinator's model sees `web_researcher` as a tool. The sub-agent runs
with its own instructions and tools inside the coordinator's conversation, so
it needs no agent of its own. In the UI, select the template under
**Sub-agents** when you create the coordinator.

## Deploy

The coordinator needs the `web-researcher` template from
[`agent-with-mcp`](../agent-with-mcp/).

```bash
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f agent.yaml
kubectl wait --for=condition=Ready agent.api.kagent.dev/research-coordinator --timeout=5m
```

## Try it

Open `research-coordinator` on the **Agents** page and ask:

```text
Research https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

The chat shows the call to `web_researcher` and, inside it, the fetch.

## Clean up

```bash
kubectl delete -f agent.yaml -f template.yaml
```
