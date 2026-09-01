# Deploy an upstream MCP server

This example deploys the upstream Time MCP server image with a ToolHive `MCPServer` resource.

```bash
export NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
kubectl apply -n "$NAMESPACE" -f time-server.yaml
kubectl get -n "$NAMESPACE" mcpservers.toolhive.stacklok.dev
```

If you are not running in a prokube Lab, set `NAMESPACE` to the target workspace
namespace instead. Always pass it explicitly because a Lab does not necessarily
have a `kubectl` current context.

The server exposes the `get_current_time` and `convert_time` tools.

The current upstream image requires root because of its image layout. Use this as a minimal ToolHive smoke test, not as a production baseline.

Continue with the parent [MCP server examples](../README.md) guide to wait for
readiness, call the tools, and connect through Agent Gateway.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f time-server.yaml
```
