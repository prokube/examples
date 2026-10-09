# Build and deploy a custom MCP server

This example builds an [MCP](https://modelcontextprotocol.io/) server with
[FastMCP](https://gofastmcp.com/) and deploys it through
[ToolHive](https://docs.stacklok.com/toolhive/). It stores Markdown notes on a
PVC and lets MCP clients list, read, save, search, and delete them.

The server is deliberately simple: notes are plain files and search is basic
case-insensitive text matching. It uses no database, embeddings, or vector
search. This keeps the focus on the complete workflow: writing a custom MCP
server, packaging it as an image, deploying it, and connecting a client.

## Prerequisites

MCP servers must be enabled on your prokube cluster (v1.9.0 or later). If
`kubectl apply` fails with the following error, ToolHive is not installed and
you need to ask your platform admin to enable MCP servers:

```text
no matches for kind "MCPServer" in version "toolhive.stacklok.dev/v1beta1"
ensure CRDs are installed first
```

## Tools

- `list_notes`: list note names
- `get_note`: return the Markdown content of a note
- `save_note`: create or replace a note
- `search_notes`: find notes whose name or content contains a text
- `delete_note`: delete a note

## How it works

- [`markdown-notes-server/server.py`](./markdown-notes-server/server.py) is the
  whole server. FastMCP turns each `@mcp.tool` function into an MCP tool and
  uses its type hints and docstring as the tool schema and description. Each
  note is a `<name>.md` file in `/data/notes`. Names are normalized to
  lowercase slugs, so `Pipeline Quota` is stored as `pipeline-quota.md`.
- When the notes directory is empty, the server copies the two sample notes
  from [`seed-notes`](./markdown-notes-server/seed-notes/), so there is
  something to list and search right away.
- [`markdown-notes.yaml`](./markdown-notes.yaml) creates a PVC and a ToolHive
  `MCPServer`. The server speaks MCP over stdio. ToolHive runs it in a Pod and
  exposes it over Streamable HTTP on port 8080, which the Agent Gateway routes
  to.
- The container runs as a non-root user with a read-only root filesystem, so
  notes can only be written to the `markdown-notes-example-data` PVC mounted at
  `/data`. Notes therefore persist across Pod restarts and redeployments.

## Image

A prebuilt image is available, so you can deploy the example as is:

```text
europe-west3-docker.pkg.dev/prokube/releases/markdown-notes-mcp:v1.0.1
```

If you change the server, follow [Build your own image](#build-your-own-image)
below and update the manifest with your image.

## Run the notebook

The easiest way to try the example is
[`markdown-notes.ipynb`](./markdown-notes.ipynb). Open it in a prokube Lab and
run its cells. It deploys the server, searches, saves, and reads notes, connects
with an API key, and cleans up.

If you prefer a terminal, follow the steps below instead.

## Deploy

From a prokube Lab terminal, use its current namespace:

```bash
kubectl apply -f markdown-notes.yaml

kubectl wait --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/markdown-notes-example --timeout=3m
```

From a terminal outside a Lab, set the workspace namespace explicitly:

```bash
export NAMESPACE=<workspace>
kubectl apply -n "$NAMESPACE" -f markdown-notes.yaml

kubectl wait -n "$NAMESPACE" --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/markdown-notes-example --timeout=3m
```

## Connect

### From a Lab

Labs reach the workspace's MCP endpoint through the internal Agent Gateway URL
without an API key. This is the same endpoint the prokube UI shows: it
aggregates all MCP servers in the workspace and prefixes each tool with its
server name, for example `markdown-notes-example_search_notes`.

Open an MCP session and keep its ID:

```bash
export MCP_URL=http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/mcp/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)

MCP_SESSION=$(curl -sS -D - -o /dev/null "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}' \
  | sed -n 's/^mcp-session-id: //Ip' | tr -d '\r')

mcp() {
  curl -sS "$MCP_URL" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H "Mcp-Session-Id: $MCP_SESSION" \
    --data "$1" | sed -n 's/^data: //p'
}

mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

The gateway responds with server-sent events. `mcp` strips the `data: ` prefix
so that `jq` can format the JSON. To debug a request, run its `curl` command
with `-v` and without the pipes.

List the tools available in the workspace. Tools of other MCP servers in the
workspace appear in this list too:

```bash
mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq -r '.result.tools[].name'
```

```text
markdown-notes-example_list_notes
markdown-notes-example_get_note
markdown-notes-example_save_note
markdown-notes-example_search_notes
markdown-notes-example_delete_note
```

Search the notes:

```bash
mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"markdown-notes-example_search_notes","arguments":{"query":"quota"}}}' \
  | jq '.result.structuredContent.result'
```

```json
[
  {
    "name": "model-endpoint-503",
    "snippet": "2. Check recent pod events for image pull, quota, or readiness errors."
  },
  {
    "name": "pipeline-quota",
    "snippet": "# Pipeline Quota"
  }
]
```

### From outside the cluster

Create a Bearer API key for `markdown-notes-example` on the **API Keys** page in the
prokube UI at `https://<your-prokube-domain>/pkui/ai-gateway/keys`. Copy the
external URL from the server's page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "markdown-notes-example": {
      "type": "http",
      "url": "https://<your-prokube-domain>/svc/mcp/<workspace>/markdown-notes-example",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

## Build your own image

After changing the server, run these commands from this example's directory in
a prokube Lab terminal. Labs use the `pk-builder` remote BuildKit service and
do not require a local Docker daemon:

```bash
export IMAGE=<registry>/<project>/markdown-notes-mcp:0.1.0
docker login <registry>
docker buildx build \
  --builder pk-builder \
  --platform linux/amd64 \
  --push \
  -t "$IMAGE" \
  markdown-notes-server
```

Replace `spec.image` in `markdown-notes.yaml` with the pushed image. Add
registry credentials to the workspace first when the image is private.

## Clean up

From a Lab:

```bash
kubectl delete -f markdown-notes.yaml
```

From outside a Lab:

```bash
kubectl delete -n "$NAMESPACE" -f markdown-notes.yaml
```

This also deletes the PVC. Export notes you want to retain before cleanup.
