# Many sandboxes in parallel

This example creates 20 sandboxes at once with `AsyncSandboxClient`, runs a
test in each and deletes them again, as an eval or a test matrix would. Each
sandbox starts from its preset's snapshot, so creating and starting it takes
well under a second.

## Prerequisites

Sandboxes must be enabled on your prokube cluster, and the Lab needs sandbox
access: when you create it, enable **Allow access to sandboxes** under
**Configurations**.

## Run the notebook

Open [`parallel-sandboxes.ipynb`](./parallel-sandboxes.ipynb) in a prokube
Lab and run its cells. On a laptop, run
`pk login https://<your-prokube-domain> --workspace <workspace>` first. The
notebook prints how long creating and starting the sandboxes took, for
example:

```text
20 sandboxes created, used and deleted in 2.1 s
create: median 0.19 s, max 0.20 s
start and test: median 0.37 s, max 0.40 s
failed: ['parallel-3', 'parallel-7', 'parallel-11', 'parallel-15', 'parallel-19']
```

## Capacity

A suspended sandbox takes no room, so creating many is cheap. A running
sandbox reserves its preset's CPU and memory (`pk preset list` shows the
size) on a worker of the sandbox pool, which all workspaces share. The
default pool has two workers with 4 CPUs and 8 GiB each, room for eight
running `small` sandboxes at a time.

When the pool is full, starting one more fails with
`no worker has room for the actor`. That is why the notebook runs at most
`RUNNING` sandboxes at the same time; set it to what is free on your cluster.
Admins see the pool's workers and the running sandboxes of all workspaces on
the **Sandbox Administration** page of the prokube UI, and change the pool's
size in the platform configuration.

## Clean up

Each sandbox is deleted after its test. If the notebook stopped before,
delete the `parallel-*` sandboxes on the **Sandboxes** page of the prokube UI,
or run [`.ci/cleanup.py`](./.ci/cleanup.py) in the Lab.
