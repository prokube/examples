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
- The notebook replaces the sandbox's network rules with three:

  - `https` for `api.anthropic.com`: the egress gateway terminates TLS and
    sets the `x-api-key` header to the key from the Secret
    (`sandboxes.secret_uri("anthropic-api-key", "ANTHROPIC_API_KEY")`). The
    presets' images trust the gateway's CA (`NODE_EXTRA_CA_CERTS`).
  - `tlsPassthrough` for `github.com` and `registry.npmjs.org`, to clone the
    repository and install Claude Code.
  - Nothing else is reachable.

- Claude Code is not part of the sandbox image. The notebook installs it into
  `/workspace` with npm and runs it there with a placeholder key:

  ```bash
  claude -p "<task>" --output-format json --permission-mode acceptEdits
  ```

  It edits the files in `/workspace/sampleproject`, a clone of
  [pypa/sampleproject](https://github.com/pypa/sampleproject), and prints its
  answer as JSON.

## Run the notebook

Open [`claude-code-worker.ipynb`](./claude-code-worker.ipynb) in a prokube Lab
and run its cells.

On a laptop, run `pk login https://<your-prokube-domain> --workspace <workspace>`
first. The notebook creates the Secret with `kubectl`, so your kubeconfig must
point at the workspace namespace.

## Use Claude Code interactively

The terminal and SSH run as the user `developer`, the notebook's commands as
`root`. Before the last cell deletes the sandbox, give the repository to
`developer` from the notebook:

```python
sandboxes.run(SANDBOX, "chown -R developer: /workspace/sampleproject")
```

Then open a shell in the sandbox, in its **Terminal** tab in the prokube UI or
with `pk sandbox connect claude-code` on a laptop, and start Claude Code:

```bash
cd /workspace/sampleproject
ANTHROPIC_API_KEY=placeholder /workspace/claude-code/node_modules/.bin/claude
```

## Clean up

The notebook's last cell deletes the sandbox; run it if the notebook stopped
before. Delete the Secret too, unless another example uses it:

```bash
kubectl delete secret anthropic-api-key
```
