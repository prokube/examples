# MCP server examples

MCP servers give agents and MCP clients access to tools. prokube runs them as
Kubernetes workloads managed by ToolHive and makes eligible servers available
through Agent Gateway.

The normal workflow is to keep the ToolHive `MCPServer` root in
version-controlled YAML and apply it with GitOps or `kubectl`. ToolHive
reconciles the runtime resources from that durable Kubernetes intent. The
prokube **MCP** page can author and inspect the same roots, but the workload does
not depend on pkui remaining installed or available.

## Examples

| Example | Use when |
|---|---|
| [`deploy-upstream-mcp-server`](./deploy-upstream-mcp-server/) | You want the shortest end-to-end example. It deploys an existing Time server, lists its tools, and calls one tool. Start here. |
| [`build-custom-mcp-server`](./build-custom-mcp-server/) | You want to build a FastMCP server, persist its data on a workspace volume, and deploy your own image. |

## Prerequisites

- Access to a prokube workspace with MCP servers enabled.
- A prokube Lab or notebook running in the target workspace.
- Permission to create ToolHive `MCPServer` resources in that workspace.

Managed Labs clone this repository into `~/examples` by default. Their in-cluster
`kubectl` access defaults to the Lab's workspace. The commands below still read
and pass that namespace explicitly so they are also safe to adapt for an
external kubeconfig that can access more than one workspace.

```bash
export NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
cd ~/examples/mcp-servers/deploy-upstream-mcp-server
```

## Quick start

Deploy the Time MCP server and wait until ToolHive reports it as ready:

```bash
kubectl apply -n "$NAMESPACE" -f time-server.yaml

kubectl wait -n "$NAMESPACE" \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/time \
  --timeout=180s

kubectl get -n "$NAMESPACE" mcpservers.toolhive.stacklok.dev/time \
  -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,URL:.status.url'
```

Use the complete `mcpservers.toolhive.stacklok.dev` resource name. Some prokube
clusters also install a kagent resource named `MCPServer`; the short name is
therefore ambiguous.

Optionally open **MCP** in prokube and select the same workspace to inspect the
externally authored root. The `time` server should appear as **Running**, with
logs, events, metrics, configuration, and connection information on its details
page.

## Call the server from the Lab

Read the workspace-internal endpoint from the ToolHive resource:

```bash
export MCP_URL="$(
  kubectl get -n "$NAMESPACE" mcpservers.toolhive.stacklok.dev/time \
    -o jsonpath='{.status.url}'
)"
```

The included client uses only the Python standard library. It performs the MCP
Streamable HTTP initialization handshake before each operation.

List the server's tools:

```bash
python ../mcp-client.py "$MCP_URL" list
```

Call `get_current_time`:

```bash
python ../mcp-client.py "$MCP_URL" call get_current_time \
  --arguments '{"timezone":"Europe/Berlin"}'
```

This direct URL is reachable from workloads in the workspace. Agents normally
discover the tools through prokube's federated workspace MCP endpoint rather
than connecting to each ToolHive Service separately.

## Call the server from outside prokube

External MCP clients use Agent Gateway and a user-managed API key:

1. In prokube, open **API Keys** and select this workspace.
2. Create a key, select the `time` MCP server, and choose either Bearer or
   `x-api-key` authentication.
3. Copy the key when prokube displays it. The value is shown only once.
4. Open the `time` server on the **MCP** page and copy its **External URL**.

Enter the copied key without putting it in shell history:

```bash
read -rsp "MCP API key: " MCP_API_KEY && echo
export MCP_API_KEY
export MCP_URL='https://<your-prokube-domain>/mcp/<workspace>/time'
```

For a Bearer key:

```bash
MCP_AUTH=bearer python ../mcp-client.py "$MCP_URL" list
```

For an `x-api-key` key:

```bash
MCP_AUTH=x-api-key python ../mcp-client.py "$MCP_URL" list
```

The examples never create API keys or Agent Gateway credentials. Key creation,
scope selection, rotation, disabling, and deletion remain user actions in the
prokube UI.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f time-server.yaml
unset MCP_API_KEY MCP_AUTH MCP_URL
```
