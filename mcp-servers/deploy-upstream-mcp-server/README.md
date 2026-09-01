# Deploy an upstream MCP server

This example deploys the upstream Time MCP server. It exposes the
`get_current_time` and `convert_time` tools.

## Deploy

```bash
export NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
kubectl apply -n "$NAMESPACE" -f time-server.yaml

kubectl wait -n "$NAMESPACE" \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/time \
  --timeout=180s
```

The image requires root because of its image layout. Use it as a quick example,
not as a production baseline.

## Connect

Create a Bearer API key for the `time` server on the **API Keys** page in the
prokube UI. Copy the external URL from the server's page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "time": {
      "type": "http",
      "url": "https://<your-prokube-domain>/mcp/<workspace>/time",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f time-server.yaml
```
