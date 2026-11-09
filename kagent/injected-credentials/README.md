# Use a password the agent never sees

An agent often needs to log in to an API. With prokube the password stays in a
Kubernetes Secret: the egress gateway adds it to the agent's requests on the
way out, so neither the model nor the code ever sees it. This example gives
`analyst` from [`allowed-hosts`](../allowed-hosts/) a login for
[httpbin.org](https://httpbin.org), a public test service.

## How it works

- The login is in the Secret `demo-api-login`, labelled
  `prokube.ai/sandbox-credential=true`. Only labelled Secrets of the workspace
  can be used as credentials.
- [`network.yaml`](./network.yaml) adds `httpbin.org` with that Secret:

  ```yaml
  - origin: https://httpbin.org
    authentication:
      header: Authorization
      prefix: "Basic "
      secretKeyRef:
        name: demo-api-login
        key: credentials
  ```

- The agent's code sends `Authorization: Basic placeholder`.
  [`template.yaml`](./template.yaml) tells it to. The gateway replaces the
  placeholder with the real value; requests without the header are passed on
  unchanged.

The same works for tokens, for example `prefix: "Bearer "` with a GitHub token
for `https://api.github.com`. In the UI, add the host under **Network and
credentials** and pick the Secret.

## Deploy

Deploy [`allowed-hosts`](../allowed-hosts/) first. A Basic login is the
base64 of `user:password`:

```bash
kubectl create secret generic demo-api-login --from-literal=credentials="$(printf 'demo:s3cret' | base64)"
kubectl label secret demo-api-login prokube.ai/sandbox-credential=true
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f network.yaml -f sandbox-template.yaml -f agent.yaml
kubectl wait --for=condition=Ready sandboxtemplate.api.kagent.dev/analyst-code agent.api.kagent.dev/analyst --timeout=5m
```

## Try it

Start a new chat with `analyst` and ask:

```text
Call https://httpbin.org/headers. In the same script, decode the Basic
Authorization header that arrived at the server and print the user name.
```

httpbin echoes the request: the code sent `Basic placeholder`, the server
received `Basic ZGVtbzpzM2NyZXQ=`, and the script prints `demo`.

## Clean up

```bash
kubectl delete -f agent.yaml -f template.yaml -f sandbox-template.yaml -f network.yaml
kubectl delete secret demo-api-login
```
