# Many sandboxes in parallel

This example creates 20 sandboxes at once with `AsyncSandboxClient`, runs a
test in each and deletes them again, as an eval or a test matrix would. Each
sandbox starts from its preset's snapshot in well under a second. Creating,
running and deleting are separate cells, so you can watch the sandboxes on
the **Sandboxes** page of the prokube UI.

## Prerequisites

Sandboxes must be enabled on your prokube cluster, and the Lab needs sandbox
access, see the [sandbox examples](../README.md).

## Run the notebook

Open [`parallel-sandboxes.ipynb`](./parallel-sandboxes.ipynb) in a prokube
Lab and run its cells. They print, for example:

```text
20 sandboxes created in 0.3 s
20 tests run in 2.6 s
failed: [3, 7, 11, 15, 19]
20 sandboxes deleted in 0.1 s
```

## Capacity

A suspended sandbox takes no room, so creating many is cheap. A running
sandbox reserves its preset's CPU and memory in the sandbox worker pool,
which all workspaces share. When the pool is full, starting one more fails
with `no worker has room for the actor`, so the notebook runs at most
`RUNNING` sandboxes at the same time; set it to what is free on your
cluster. See [Capacity](https://prokube.ai/docs/development/admin/sandboxes.html#capacity)
in the admin documentation.

## Clean up

The last cell deletes the sandboxes. If the notebook stopped before, run it,
or delete the `parallel-*` sandboxes on the **Sandboxes** page.
