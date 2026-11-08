# GitHub agent with an injected token

An agent that answers questions about GitHub repositories by writing Python and
running it in its own sandboxes. It calls the GitHub API with a token it never
sees, and it can install packages from PyPI. Nothing else on the internet is
reachable.

## Prerequisites

- Agents are enabled for your workspace (the **Agents** page is available).
- A model configuration in the workspace, for example one granted through the
  AI Gateway. Its name goes into `MODEL_CONFIG` below.
- A GitHub token. A fine-grained token with read access to public repositories
  is enough.

## How it works

- The token is in the Secret `github-token` with the label
  `prokube.ai/sandbox-credential=true`. Only labelled Secrets of the workspace
  can be used as credentials.
- [`manifests/network.yaml`](./manifests/network.yaml) is the agent's network
  setting: `api.github.com` with the token, plus `pypi.org` and
  `files.pythonhosted.org`. The egress gateway replaces the `Authorization`
  header on the way out.
- [`manifests/agent-template.yaml`](./manifests/agent-template.yaml) gives the
  agent its prompt and the sandbox tools.
  [`manifests/sandbox-template.yaml`](./manifests/sandbox-template.yaml) is the
  Python environment it runs code in, and
  [`manifests/agent.yaml`](./manifests/agent.yaml) the agent itself. The agent
  and the sandbox template both use the network setting, so code in the
  sandbox reaches the same hosts.

The same setup can be clicked together in the UI: create the agent with
**Run code** and add the hosts and the credential under **Network and
credentials**. Agents have no shell of their own, so code always runs in these
sandboxes.

## Deploy

The sandbox tools come from the `kagent-api` tool server. If no agent in the
workspace uses **Run code** yet, enable it once on any agent, or create the
server under **Tools**.

```bash
kubectl create secret generic github-token -n <workspace> --from-literal=token=<your-github-token>
kubectl label secret github-token -n <workspace> prokube.ai/sandbox-credential=true
sed 's/MODEL_CONFIG/<your-model-config>/' manifests/agent-template.yaml | kubectl apply -n <workspace> -f -
kubectl apply -n <workspace> -f manifests/network.yaml -f manifests/sandbox-template.yaml -f manifests/agent.yaml
```

## Try it

Open the agent on the **Agents** page and ask, for example:

> How many open issues labelled "bug" does kubernetes/kubernetes have? Use the
> GitHub API with PyGithub.

The tool activity shows the sandbox it creates, the `pip install`, and the
script. Asking it to fetch `https://example.com` fails: that host is not
allowed.

## Clean up

```bash
kubectl delete -n <workspace> -f manifests/
kubectl delete secret github-token -n <workspace>
```
