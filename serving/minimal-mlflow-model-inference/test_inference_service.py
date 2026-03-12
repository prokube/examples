# Test the deployed InferenceService.
# The deployed service is protected by an API Key.
import argparse
import json as jsonlib
import os
from getpass import getpass

import requests

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

if PROTOCOL_VERSION == "v2":
    url = f"{INFERENCE_SERVICE_URI}/{PROTOCOL_VERSION}/models/{INFERENCE_SERVICE_NAME}/infer"
else:
    url = f"{INFERENCE_SERVICE_URI}/{PROTOCOL_VERSION}/models/{INFERENCE_SERVICE_NAME}:predict"

response = requests.post(
    url,
    headers={"X-Api-Key": INFERENCE_SERVICE_API_KEY},
    json=request_body,
)
print(response.json())
