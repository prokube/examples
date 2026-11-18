# Allow an agent a few hosts

Agents and their sandboxes reach nothing on the internet by default, apart
from their model and MCP servers. This example lets `analyst` from
[`run-code`](../run-code/) install packages from PyPI and read weather data
from Open-Meteo, and nothing else.

## How it works

[`network.yaml`](./network.yaml) is an EgressPolicy with three hosts:

```yaml
destinations:
- origin: https://pypi.org
- origin: https://files.pythonhosted.org
- origin: https://api.open-meteo.com
```

[`agent.yaml`](./agent.yaml) and
[`sandbox-template.yaml`](./sandbox-template.yaml) both reference it, so the
agent and the code it runs share the same rules. The platform's egress gateway
enforces them; requests to any other host fail.

In the UI, add the hosts under **Network and credentials** on the agent.
Policies that several agents share are managed on the **Egress policies** tab.

## Deploy

Deploy [`run-code`](../run-code/) first, then:

```bash
kubectl apply -f network.yaml -f sandbox-template.yaml -f agent.yaml
kubectl wait --for=condition=Ready sandboxtemplate.api.kagent.dev/analyst-code agent.api.kagent.dev/analyst --timeout=5m
```

## Try it

Start a new chat with `analyst` and ask:

```text
Install the requests package, then use the Open-Meteo forecast API to get the
current temperature in Berlin. Afterwards try to fetch https://example.com and
tell me what happened.
```

The `pip install` and the weather request succeed; `example.com` fails with a
connection error.

## Clean up

Skip this if you continue with
[`injected-credentials`](../injected-credentials/).

```bash
kubectl delete -f agent.yaml -f template.yaml -f sandbox-template.yaml -f network.yaml
```
