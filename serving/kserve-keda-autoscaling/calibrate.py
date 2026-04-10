#!/usr/bin/env python3
"""Calibrate KEDA token-throughput threshold for vLLM on a single replica.

This script steps through increasing concurrency, measures throughput and mean
end-to-end latency from vLLM metrics, and suggests a threshold at ~80% of the
last pre-plateau throughput.

Usage (run from a notebook terminal inside the cluster):
    python calibrate.py --url http://my-model-predictor/openai/v1/completions --model my-model

Press Ctrl+C to stop at any time.
"""

import argparse
import json
import math
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_STEPS = [1, 2, 4, 8, 16]
DEFAULT_STEP_DURATION = 30

DEFAULT_URL = "http://opt-125m-predictor/openai/v1/completions"
DEFAULT_MODEL = "opt-125m"
DEFAULT_MAX_TOKENS = 200
DEFAULT_PROMPT = (
    "Write a long detailed story about a dragon who discovers a hidden kingdom"
)


def send_request(url: str, model: str, prompt: str, max_tokens: int) -> dict | None:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def worker_loop(
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    stop: threading.Event,
    totals: dict,
    lock: threading.Lock,
) -> None:
    while not stop.is_set():
        result = send_request(url, model, prompt, max_tokens)
        with lock:
            if result and "usage" in result:
                totals["tokens"] += result["usage"].get("total_tokens", 0)
            else:
                totals["errors"] += 1


def metrics_url_from_completions_url(completions_url: str) -> str:
    parsed = urlparse(completions_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/metrics"


def fetch_metrics(metrics_url: str) -> str:
    try:
        with urllib.request.urlopen(metrics_url, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError):
        return ""


def parse_metric(metrics_text: str, prefix: str) -> float:
    for line in metrics_text.splitlines():
        if line.startswith(prefix) and not line.startswith("# "):
            try:
                return float(line.split()[-1])
            except ValueError:
                pass
    return 0.0


def snapshot_metrics(metrics_url: str) -> dict:
    text = fetch_metrics(metrics_url)
    return {
        "latency_count": parse_metric(text, "vllm:e2e_request_latency_seconds_count{"),
        "latency_sum": parse_metric(text, "vllm:e2e_request_latency_seconds_sum{"),
    }


def run_calibration(args: argparse.Namespace) -> None:
    metrics_url = metrics_url_from_completions_url(args.url)

    print("=== vLLM single-replica throughput calibration ===")
    print(f"  URL:        {args.url}")
    print(f"  Model:      {args.model}")
    print(f"  Metrics:    {metrics_url}")
    print(f"  Duration:   {DEFAULT_STEP_DURATION}s per concurrency step")
    print(f"  Max tokens: {args.max_tokens}")
    print()
    print("Make sure only ONE replica is running and there is no other traffic.")
    print("The ScaledObject (if deployed) should be deleted or paused first.")
    print()

    if not fetch_metrics(metrics_url):
        print(f"ERROR: could not reach metrics endpoint at {metrics_url}")
        print(
            "Check that the service URL is correct and reachable from this pod/notebook."
        )
        return

    print(
        f"  {'Concurrency':<12} {'Throughput (tok/s)':<22} {'Mean latency (s)':<20} Note"
    )
    print(
        f"  {'-----------':<12} {'------------------':<22} {'----------------':<20} ----"
    )

    prev_rate = 0.0
    best_rate = 0.0

    try:
        for concurrency in DEFAULT_STEPS:
            snap_before = snapshot_metrics(metrics_url)
            t0 = time.time()

            stop = threading.Event()
            totals = {"tokens": 0, "errors": 0}
            lock = threading.Lock()
            threads = []

            for _ in range(concurrency):
                t = threading.Thread(
                    target=worker_loop,
                    args=(
                        args.url,
                        args.model,
                        args.prompt,
                        args.max_tokens,
                        stop,
                        totals,
                        lock,
                    ),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            try:
                stop.wait(timeout=DEFAULT_STEP_DURATION)
            except KeyboardInterrupt:
                print("\nInterrupted — stopping current step.")
                stop.set()
                for t in threads:
                    t.join(timeout=10)
                raise

            stop.set()
            for t in threads:
                t.join(timeout=10)

            elapsed = time.time() - t0
            snap_after = snapshot_metrics(metrics_url)

            with lock:
                step_tokens = totals["tokens"]
                step_errors = totals["errors"]

            rate = step_tokens / elapsed if elapsed > 0 else 0.0

            delta_count = snap_after["latency_count"] - snap_before["latency_count"]
            delta_sum = snap_after["latency_sum"] - snap_before["latency_sum"]
            mean_lat = f"{delta_sum / delta_count:.2f}" if delta_count > 0 else "n/a"

            note = ""
            plateau = prev_rate > 0 and (rate - prev_rate) / prev_rate < 0.15
            if plateau:
                note = "<-- plateau, saturation likely here"
            else:
                best_rate = rate

            err_note = f" ({step_errors} errors)" if step_errors else ""
            print(f"  {concurrency:<12} {rate:<22.1f} {mean_lat:<20} {note}{err_note}")
            prev_rate = rate

            if plateau and concurrency >= 4:
                break

    except KeyboardInterrupt:
        print()

    print()
    print("Find the last step where throughput was still growing.")
    print("Set your KEDA threshold to ~80% of its tok/s value.")
    print()
    threshold_suggestion = math.floor(best_rate * 0.8) if best_rate > 0 else "?"
    print(
        f"  Suggested threshold (80% of last pre-plateau rate): {threshold_suggestion} tok/s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate KEDA threshold from vLLM throughput plateau"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Completions endpoint URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model name to use in requests (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens per request (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt text",
    )
    args = parser.parse_args()
    run_calibration(args)


if __name__ == "__main__":
    main()
