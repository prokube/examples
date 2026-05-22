# Local registry mode

The notebook talks to the registry via a **local SQLite SQL file** written
directly by the Feast SDK — no gRPC server involved.

## How it works

- `feast apply` writes feature definitions to `sqlite:////tmp/registry.db`
  (or a mounted PVC path — see `feature_store.yaml`).
- The registry is read back from the same file. No network hop, no Istio
  concerns, no protocol negotiation.
- ODFVs (on-demand feature views) work without workarounds.

## Trade-offs vs remote mode

| | Local (this folder) | Remote |
|---|---|---|
| Registry persistence | Ephemeral (`/tmp`) by default | Persistent on operator PVC |
| Shared across clients | No — each notebook has its own `/tmp` | Yes — all clients in the namespace see the same definitions |
| ODFVs | Work out of the box | Require a monkey-patch workaround (Feast ≤ 0.63 bug) |
| Istio workaround | Not needed | Required (3-part) |
| Setup complexity | Low | Higher |

## When to use

Use local mode when:
- You are the only user of this feature store
- You want ODFVs without workarounds
- You are experimenting or iterating quickly

Switch to remote mode when feast-dev/feast#6367 is merged (operator sets
`appProtocol: grpc` on its own Service) — at that point the Istio workaround
collapses and remote becomes the clear default.

## Files

| File | Purpose |
|------|---------|
| `feast-cr.yaml` | FeatureStore CR — no `server: {}`, registry PVC only |
| `feature_store.yaml` | Feast SDK config template (notebook writes this) |
