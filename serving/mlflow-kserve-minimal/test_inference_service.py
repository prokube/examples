# Test the deployed InferenceService.
# The deployed service is protected by an API Key.
import argparse
import json as jsonlib
import os
import subprocess
import sys
from getpass import getpass

import requests

try:
    from pk_helpers import external_predict_url
except ImportError:
    # Lets this script run standalone, not just via apply.py (which already
    # ensures pk_helpers in its own preflight step).
    repo_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
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
response = requests.post(
    url, headers={"X-Api-Key": INFERENCE_SERVICE_API_KEY}, json=request_body
)
try:
    response.raise_for_status()
except requests.HTTPError as exc:
    raise RuntimeError(f"inference request failed: {response.text}") from exc
result = response.json()

pred_key = "outputs" if PROTOCOL_VERSION == "v2" else "predictions"
if pred_key not in result:
    raise RuntimeError(f"unexpected response body: {result}")
print(result)
