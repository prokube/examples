# Call an agent from your code

This example sends a message to an agent from outside the cluster, for example
from an application, a CI job or another agent framework. It uses
`simple-assistant` from [`basic-agent`](../basic-agent/).

## How it works

Agents speak [A2A](https://a2a-protocol.org/). Agent Gateway publishes each
agent at `https://<your-prokube-domain>/svc/a2a/<workspace>/<agent>` and
accepts requests with an API key. Conversations started with the key belong to
the key's owner.

[`a2a_client.py`](./a2a_client.py) sends one `SendStreamingMessage` request and
prints the agent's answer.

## Create an API key

On the **API Keys** page in the prokube UI, create a key in Bearer format and
limit it to the agent `simple-assistant`.

## Try it

```bash
pip install httpx
export A2A_URL=https://<your-prokube-domain>/svc/a2a/<workspace>/simple-assistant
export PROKUBE_API_KEY=<your-api-key>
python a2a_client.py "What can you help me with?"
```

A key for another agent or another workspace is rejected. Use the gateway URL
above rather than the URL in the agent card, which is internal to the cluster.

## Clean up

Delete the key on the **API Keys** page.
