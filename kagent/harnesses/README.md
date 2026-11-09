# Run agents on Claude Code and Codex

A harness is the runtime an agent runs on. The examples so far use `default`,
the kagent runtime. The Claude and Codex harnesses run Anthropic's Claude Code
and OpenAI's Codex instead, with their own shell and file tools inside the
agent. This example creates one coding agent on each.

## How it works

- [`claude-harness.yaml`](./claude-harness.yaml) and
  [`codex-harness.yaml`](./codex-harness.yaml) create the harnesses `claude`
  and `codex` on the platform's shared workers. Create them once; any agent in
  the workspace can use them.
- [`coder-claude.yaml`](./coder-claude.yaml) and
  [`coder-codex.yaml`](./coder-codex.yaml) are the agents. Their instructions
  are inline instead of in a separate AgentTemplate.
- [`network.yaml`](./network.yaml) allows PyPI. The rules apply to everything
  the agent's shell does, as in [`allowed-hosts`](../allowed-hosts/).

Claude Code needs an Anthropic model, Codex an OpenAI model that supports the
Responses API. Both use your own provider key; the platform adds it on the way
out, as in [`basic-agent`](../basic-agent/).

In the UI, create the harnesses on the **Harnesses** tab and select one under
**Runs on** when creating an agent.

## Deploy

```bash
kubectl apply -f claude-harness.yaml -f codex-harness.yaml -f network.yaml
```

Claude Code, with the Anthropic model configuration from
[`basic-agent`](../basic-agent/):

```bash
sed 's/ANTHROPIC_MODEL_CONFIG/anthropic-haiku/' coder-claude.yaml | kubectl apply -f -
kubectl wait --for=condition=Ready agent.api.kagent.dev/coder-claude --timeout=5m
```

Codex, with your OpenAI key:

```bash
kubectl create secret generic openai-api-key --from-literal=OPENAI_API_KEY=<your-api-key>
kubectl label secret openai-api-key prokube.ai/sandbox-credential=true
kubectl apply -f openai-model.yaml
sed 's/OPENAI_MODEL_CONFIG/openai-gpt/' coder-codex.yaml | kubectl apply -f -
kubectl wait --for=condition=Ready agent.api.kagent.dev/coder-codex --timeout=5m
```

Or with an OpenAI model an administrator granted through AI Gateway: copy its
model configuration with the Responses format.

```bash
kubectl get modelconfig <granted-model> -o json \
  | jq '.metadata = {name: "codex-model"} | .spec.openAI.apiFormat = "responses"' \
  | kubectl apply -f -
sed 's/OPENAI_MODEL_CONFIG/codex-model/' coder-codex.yaml | kubectl apply -f -
```

## Try it

Open `coder-claude` on the **Agents** page and ask:

```text
Compute the 40th Fibonacci number in your shell. Then use wget to get the
latest version of requests from https://pypi.org/pypi/requests/json, and try
wget https://example.com.
```

The chat shows each shell command. The answer is 102334155, PyPI answers, and
`example.com` cannot be reached. The Claude Code image is minimal: it has
`bash` and `wget`, but no Python.

## Clean up

```bash
kubectl delete -f coder-claude.yaml -f coder-codex.yaml -f network.yaml
kubectl delete -f claude-harness.yaml -f codex-harness.yaml
kubectl delete -f openai-model.yaml --ignore-not-found
kubectl delete modelconfig codex-model --ignore-not-found
kubectl delete secret openai-api-key --ignore-not-found
```
