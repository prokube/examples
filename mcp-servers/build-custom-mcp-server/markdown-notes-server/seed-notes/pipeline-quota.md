# Pipeline Quota

## Symptoms

- Pipeline steps stay pending.
- New pods are not created in the workspace namespace.

## Checks

1. Check workspace pod quota in the prokube UI.
2. Delete completed pods if the workspace is at its pod limit.
3. Check whether other workloads are consuming CPU or memory requests.
4. Retry the run after capacity is available.

## Escalate

Escalate if active workloads are expected and the workspace needs a quota increase.
