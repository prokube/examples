# Claude Code as a headless worker

This example runs [Claude Code](https://code.claude.com/docs/en/overview)
non-interactively in a prokube sandbox on a Git repository and returns its
answer and the diff. The Anthropic API key never enters the sandbox.

## Prerequisites

Sandboxes must be enabled on your prokube cluster, and the Lab needs sandbox
access: when you create it, enable **Allow access to sandboxes** under
**Configurations**. You also need an Anthropic API key.

## How it works

- The key is in the Secret `anthropic-api-key` with the label
  `prokube.ai/sandbox-credential=true`. Sandboxes can use labelled Secrets of
  their own workspace at egress, and no others.
- The notebook creates the sandbox with its own network rules instead of the
  preset's. For `api.anthropic.com`, the egress gateway terminates TLS and sets
  the `x-api-key` header to the key from the Secret; the presets' images trust
  the gateway's CA. `github.com` and `registry.npmjs.org` pass through
  unchanged. Nothing else is reachable.
- Claude Code is not part of the sandbox image. The notebook installs it into
  `/workspace` with npm and runs one task with a placeholder key in a clone
  of [pypa/sampleproject](https://github.com/pypa/sampleproject).

## Run the notebook

Open [`claude-code-worker.ipynb`](./claude-code-worker.ipynb) in a prokube Lab
and run its cells. To run it on a laptop, log in first as described in the
[sandbox examples](../README.md), with your kubeconfig pointing at the
workspace for the Secret.

## Clean up

The notebook's last cell deletes the sandbox; run it if the notebook stopped
before. Delete the Secret when no other example uses it:

```bash
kubectl delete secret anthropic-api-key
```
