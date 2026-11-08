# Create a basic agent

This example creates a simple agent without tools.

## How it works

[`template.yaml`](./template.yaml) is an AgentTemplate: it names a model
configuration and sets the instructions.
[`agent.yaml`](./agent.yaml) runs that template on the workspace's `default`
harness.

## Choose a model

On the **Agents** page, open **Models**. Models granted by your administrator
are listed with origin **AI Gateway** and need no API key. Note the name of the
one you want to use.

To use your own provider key instead, store it in a Secret and create a
ModelConfig. The label lets the platform use the Secret as a credential:

```bash
kubectl create secret generic anthropic-api-key --from-literal=ANTHROPIC_API_KEY=<your-api-key>
kubectl label secret anthropic-api-key prokube.ai/sandbox-credential=true
kubectl apply -f anthropic-model.yaml
```

The agent never sees the key: the platform adds it to the model requests on
their way out.

## Deploy

In the UI, select **Create agent**, enter the name and instructions, and pick
the model.

With `kubectl`, replace `MODEL_CONFIG` with the model's name:

```bash
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f agent.yaml
kubectl wait --for=condition=Ready agent.api.kagent.dev/simple-assistant --timeout=5m
```

## Try it

Open `simple-assistant` on the **Agents** page and start a chat. To call it
from code, see [`a2a-client`](../a2a-client/).

## Clean up

```bash
kubectl delete -f agent.yaml -f template.yaml
```

The next examples reuse your model configuration.
