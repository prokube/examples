# Test the deployed InferenceService.
# The deployed service is protected by an API Key.
import argparse
import json as jsonlib
import os
import subprocess
import sys
import time
from getpass import getpass

import requests

try:
    from pk_helpers import external_predict_url
except ImportError:
    # Lets this script run standalone, not just via apply.py (which already
    # ensures pk_helpers in its own preflight step).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    user_flag = [] if sys.prefix != sys.base_prefix else ["--user"]
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", *user_flag, "-e", repo_root],
        check=True,
    )
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from pk_helpers import external_predict_url

parser = argparse.ArgumentParser(description="Test the deployed InferenceService.")
parser.add_argument(
    "--json",
    "-j",
    required=True,
    help="Path to the JSON file containing the request body.",
)
parser.add_argument(
    "--model",
    "-m",
    required=True,
    help="Model name to target.",
)
args = parser.parse_args()

INFERENCE_SERVICE_API_KEY = os.getenv("API_KEY")
INFERENCE_SERVICE_URI = os.getenv("INFERENCE_SERVICE_URI")
PROTOCOL_VERSION = os.getenv("PROTOCOL_VERSION", "v2")
INFERENCE_SERVICE_NAME = args.model
JSON_FILE_PATH = args.json

if not INFERENCE_SERVICE_API_KEY:
    INFERENCE_SERVICE_API_KEY = getpass(prompt="Please enter your API key: ")
if not INFERENCE_SERVICE_URI:
    INFERENCE_SERVICE_URI = input("Please enter the external inference URI: ")

# Read the JSON body from the provided file path
with open(JSON_FILE_PATH, "r") as f:
    request_body = jsonlib.load(f)

url = external_predict_url(
    INFERENCE_SERVICE_URI, INFERENCE_SERVICE_NAME, protocol=PROTOCOL_VERSION
)
# On Agent Gateway clusters the route is created only after the ISVC reports
# Ready, so the first requests can 404 or fail to connect.
RETRY_STATUSES = {404, 502, 503}
deadline = time.monotonic() + 120
while True:
    try:
        response = requests.post(
            url,
            headers={"X-Api-Key": INFERENCE_SERVICE_API_KEY},
            json=request_body,
            timeout=30,
        )
        if response.status_code not in RETRY_STATUSES:
            break
        last_error = f"HTTP {response.status_code}: {response.text}"
    except (requests.ConnectionError, requests.Timeout) as exc:
        last_error = str(exc)
    if time.monotonic() >= deadline:
        raise RuntimeError(f"inference request failed after retries: {last_error}")
    time.sleep(5)
try:
    response.raise_for_status()
except requests.HTTPError as exc:
    raise RuntimeError(f"inference request failed: {response.text}") from exc
result = response.json()

pred_key = "outputs" if PROTOCOL_VERSION == "v2" else "predictions"
if pred_key not in result:
    raise RuntimeError(f"unexpected response body: {result}")
print(result)
