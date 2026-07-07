# Deploy an upstream MCP server

This example deploys the upstream Time MCP server image with a ToolHive `MCPServer` resource.

```bash
kubectl apply -n "$NAMESPACE" -f time-server.yaml
kubectl get mcpservers.toolhive.stacklok.dev -n "$NAMESPACE"
```

The server exposes the `get_current_time` and `convert_time` tools.

The current upstream image requires root because of its image layout. Use this as a minimal ToolHive smoke test, not as a production baseline.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f time-server.yaml
```
