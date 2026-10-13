# Give an agent MCP tools

This example adds web access to a kagent agent through MCP. It builds on the
[`basic-agent`](../basic-agent/) example and reuses its ModelConfig.

First deploy the Fetch server from the
[`mcp-servers/deploy-upstream-mcp-server`](../../mcp-servers/deploy-upstream-mcp-server/)
example. prokube then publishes the workspace's MCP tools through the
`gateway-mcp` `RemoteMCPServer`. This platform-managed resource connects kagent
to the workspace's internal MCP route; you do not need to create it yourself.
See [MCP Federation and Tool Selection](https://prokube.ai/docs/1.9/agentops/agent_gateway.html#mcp-federation-and-tool-selection)
for details.

## Prerequisites

kagent must be enabled on your prokube cluster together with MCP servers. The
agent uses Anthropic Claude through the `anthropic-haiku` ModelConfig, so you
need an Anthropic API key. The terminal steps below expect the Secret and
ModelConfig from [`basic-agent`](../basic-agent/#create-the-credentials) to
exist. If `kubectl apply` fails with the following error, kagent is not installed and you
need to ask your platform admin to enable it:

```text
no matches for kind "Agent" in version "kagent.dev/v1alpha2"
ensure CRDs are installed first
```

## Run the notebook

The easiest way to try the example is
[`web-researcher.ipynb`](./web-researcher.ipynb). Open it in a prokube Lab and
run its cells.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal and use its current workspace namespace. From another
terminal, add `-n <workspace>` to each `kubectl` command.

## Deploy

Wait until kagent has discovered the workspace MCP tools:

```bash
kubectl wait --for=condition=Accepted \
  remotemcpservers.kagent.dev/gateway-mcp --timeout=3m

kubectl get remotemcpservers.kagent.dev gateway-mcp \
  -o jsonpath='{.status.discoveredTools[*].name}{"\n"}'
```

With only the Fetch server deployed, the output includes `fetch`. The agent
manifest uses `toolNames` to grant access to that tool only. When the workspace
contains more than one MCP server, Agent Gateway prefixes each tool with its
server name, so the tool is `fetch-example_fetch`. In that case, replace `fetch`
in `web-researcher.yaml` with the name shown by the command above.

Create the agent:

```bash
kubectl apply -f web-researcher.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/web-researcher --timeout=3m
```

## Try it

Open **Agents** in the prokube UI (see
[Agents](https://prokube.ai/docs/1.9/agentops/agents.html)), select
`web-researcher`, and ask:

```text
Fetch https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

From a Lab in the workspace, send the same request without an API key:

```bash
export A2A_URL=http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)/web-researcher

a2a() {
  curl -sS "$A2A_URL" "${@:2}" \
    -H 'Content-Type: application/json' \
    --data "$(jq -n --arg text "$1" '{jsonrpc: "2.0", id: "1", method: "message/send",
      params: {message: {role: "user", messageId: "message-1", parts: [{kind: "text", text: $text}]}}}')" \
    | jq -r '.result.artifacts[0].parts[0].text'
}

a2a 'Fetch https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL.'
```

`a2a` sends one A2A `message/send` request with the given text and prints the
agent's answer. It passes further arguments to `curl`, so add `-v` to debug a
request.

From outside the cluster, create a Bearer API key for `web-researcher` on the
[API Keys page](/pkui/ai-gateway/keys) in the prokube UI
(`https://<your-prokube-domain>/pkui/ai-gateway/keys`). Then point `a2a` at the
agent's external route and pass the key:

```bash
export A2A_URL=https://<your-prokube-domain>/svc/a2a/<workspace>/web-researcher
a2a 'Fetch https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL.' -H 'Authorization: Bearer <API_KEY>'
```

## Clean up

Skip this step if you continue with [`multi-agent`](../multi-agent/), which
uses `web-researcher`.

```bash
kubectl delete -f web-researcher.yaml
```

This leaves the basic agent, ModelConfig, Secret, and Fetch server unchanged.

## Connect other MCP servers

This example uses the platform-managed `gateway-mcp`. To explore how kagent
connects to external MCP servers, you can also register an MCP endpoint as a
dedicated `RemoteMCPServer` under a different name. See the upstream
[MCP tools guide](https://kagent.dev/docs/kagent/0.x/getting-started/first-mcp-tool/)
for that workflow.
