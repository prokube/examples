# Local registry mode

The notebook talks to the registry via a **local SQLite SQL file** written
directly by the Feast SDK — no gRPC server involved.

## How it works

- `feast apply` writes feature definitions to `sqlite:////tmp/registry.db`
  (or a mounted PVC path — see `feature_store.yaml`).
- The registry is read back from the same file. No network hop, no protocol
  negotiation.
- ODFVs (on-demand feature views) work without workarounds.

## Trade-offs vs remote mode

| | Local (this folder) | Remote |
|---|---|---|
| Registry persistence | Ephemeral (`/tmp`) by default | Persistent on operator PVC |
| Shared across clients | No — each notebook has its own `/tmp` | Yes — all clients in the namespace see the same definitions |
| Setup complexity | Low | Higher |

## When to use

Use local mode when:
- You are the only user of this feature store
- You are experimenting or iterating quickly

Use remote mode when you need definitions to persist across pod restarts or
be shared with other clients in the namespace.

## Files

| File | Purpose |
|------|---------|
| `feast-cr.yaml` | FeatureStore CR — no `server: {}`, registry PVC only |
| `feature_store.yaml` | Feast SDK config template (notebook writes this) |
