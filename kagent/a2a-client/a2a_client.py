"""Send one message to a kagent agent through Agent Gateway and print the answer."""

import json
import os
import sys
import uuid

import httpx

url = os.environ["A2A_URL"]  # https://<domain>/svc/a2a/<workspace>/<agent>
api_key = os.environ["PROKUBE_API_KEY"]
text = " ".join(sys.argv[1:]) or "What can you help me with?"

request = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendStreamingMessage",
    "params": {
        "message": {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_USER",
            "parts": [{"text": text}],
        }
    },
}
headers = {"Authorization": f"Bearer {api_key}", "A2A-Version": "1.0"}

answer = ""
with httpx.stream("POST", url, json=request, headers=headers, timeout=300) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        task = json.loads(line[6:]).get("result", {}).get("task")
        for artifact in (task or {}).get("artifacts", []):
            answer = "".join(part.get("text", "") for part in artifact["parts"])

print(answer)
