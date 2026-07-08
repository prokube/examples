# Deploy an upstream MCP server

This example deploys the upstream Time MCP server image with a ToolHive `MCPServer` resource.

```bash
kubectl apply -f time-server.yaml
kubectl get mcpservers.toolhive.stacklok.dev
```

If your kubeconfig can access multiple namespaces, set the target workspace namespace explicitly, for example with `kubectl --namespace <workspace-namespace> apply -f time-server.yaml`.

The server exposes the `get_current_time` and `convert_time` tools.

The current upstream image requires root because of its image layout. Use this as a minimal ToolHive smoke test, not as a production baseline.

## Clean up

```bash
kubectl delete -f time-server.yaml
```
