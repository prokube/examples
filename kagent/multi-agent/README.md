# Delegate to another agent

This example adds agent-to-agent delegation. It builds on
[`agent-with-mcp`](../agent-with-mcp/): the coordinator invokes the
`web-researcher`, which uses the Fetch MCP server.

## Prerequisites

kagent must be enabled on your prokube cluster together with MCP servers. If
`kubectl apply` fails with the following error, kagent is not installed and you
need to ask your platform admin to enable it:

```text
no matches for kind "Agent" in version "kagent.dev/v1alpha2"
ensure CRDs are installed first
```

## Run the notebook

The easiest way to try the example is
[`research-coordinator.ipynb`](./research-coordinator.ipynb). Open it in a
prokube Lab and run its cells. It creates the prerequisites that are missing,
including `web-researcher`, deploys the coordinator, sends it a request from the
Lab and with an API key, and cleans up.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal and use its current workspace namespace. From another
terminal, add `-n <workspace>` to each `kubectl` command.

## Deploy

```bash
kubectl apply -f research-coordinator.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/research-coordinator --timeout=3m
```

## Try it

Open **Agents** in the prokube UI, select `research-coordinator`, and ask:

```text
Research https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

The coordinator delegates the request to `web-researcher`, which fetches the
page through MCP.

From a Lab in the workspace, send the same request without an API key:

```bash
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)/research-coordinator \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Research https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

From outside the cluster, create a Bearer API key for `research-coordinator` on
the **API Keys** page at `https://<your-prokube-domain>/pkui/ai-gateway/keys`
and use the external route:

```bash
curl -sS https://<your-prokube-domain>/svc/a2a/<workspace>/research-coordinator \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Research https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

## Clean up

```bash
kubectl delete -f research-coordinator.yaml
```

This leaves the agents and resources from the earlier examples unchanged.
