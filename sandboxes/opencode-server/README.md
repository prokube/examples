# opencode server in a sandbox

This example runs an [opencode](https://opencode.ai) server in a prokube
sandbox and drives it from the opencode client on your laptop. The agent
edits files and runs commands in the sandbox; the laptop only shows the
session.

## Prerequisites

Sandboxes must be enabled on your prokube cluster. On your laptop you need
[opencode](https://opencode.ai/docs/#install), an SSH key
(`ssh-keygen -t ed25519` if you have none) and the `pk` CLI with a login:

```bash
pip install 'prokube-sdk[cli] @ git+https://github.com/prokube/prokube-sdk@sandboxv3/main'
pk login https://<your-prokube-domain> --workspace <workspace>
```

## Start the server

Create the sandbox and open a shell in it:

```bash
pk sandbox create opencode --preset pk-default-small-memory --connect
```

opencode is part of the sandbox image. In the sandbox, log in to your model
provider once, then start the server in tmux so it keeps running after you
log out:

```bash
opencode auth login
mkdir -p /workspace/project && cd /workspace/project
tmux new -d -s opencode 'opencode serve --port 4096'
exit
```

The provider key is stored in the sandbox's `/workspace`. To keep keys out of
the sandbox, inject them at egress as in
[`claude-code-worker`](../claude-code-worker/).

## Attach from your laptop

Forward the port and attach in a second terminal:

```bash
pk sandbox forward opencode 4096
```

```bash
opencode attach http://localhost:4096
```

The server needs no password of its own. It listens on 127.0.0.1 in the
sandbox, so only the SSH tunnel reaches it. `pk sandbox forward` opens that
tunnel with your login, through prokube, which lets only editors of the
workspace through, and binds the port on your laptop to localhost only.

## Suspend and resume

```bash
pk sandbox suspend opencode
pk sandbox resume opencode
```

The `-memory` presets snapshot the sandbox's memory, so the opencode server
and its sessions survive suspend and resume. Start `pk sandbox forward` again
and keep working. With a preset that only keeps volumes, such as
`pk-default-small`, the sandbox restarts from `/workspace` and you start the
server again.

## Clean up

```bash
pk sandbox delete opencode
```
