#!/usr/bin/env python3
"""Load generator for vLLM-based KServe InferenceService autoscaling demos.

Modes:

  stable-2   - Sustained moderate load (~8 tok/s*) that scales to 2 replicas and holds
  stable-3   - Sustained heavy load (~22 tok/s*) that scales to 3 replicas and holds
  custom     - Specify your own --workers and --sleep values

* Rates are calibrated for opt-125m on CPU with the default prompt and max-tokens.
  Use --mode custom with your own --workers/--sleep for other models.

Usage (run from a notebook terminal inside the cluster):
    python load-generator.py --mode stable-2
    python load-generator.py --mode stable-3 --duration 300
    python load-generator.py --mode custom --workers 3 --sleep 1.0

Press Ctrl+C to stop at any time.
"""

import argparse
import json
import signal
import threading
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Preset configurations
#
# Each preset defines (workers, sleep_between_requests).
# "workers" is the number of concurrent request loops.
# "sleep_between_requests" is how long each worker pauses (seconds) after
# receiving a response before sending the next request.
#
# The ScaledObject uses:
#   metricType: AverageValue   (total metric value / current replicas)
#   threshold: 5               (tokens/sec per replica)
#
# HPA computes:  desiredReplicas = ceil(total_tok_per_sec / threshold)
#
#   stable-2:  target ~8 tok/s total   -> ceil(8/5) = 2
#   stable-3:  target ~22 tok/s total  -> ceil(22/5) = 5, capped at maxReplicas=3
#
# Calibrated for opt-125m on CPU (float32, --max-model-len=512).
# Each request averages ~116 tokens and ~6.7s of processing time.
# Effective rate per worker ≈ 116 / (6.7 + sleep) tok/s.
# ---------------------------------------------------------------------------

PRESETS = {
    "stable-2": {"workers": 1, "sleep": 8.0},
    "stable-3": {"workers": 2, "sleep": 2.0},
}

# Default model endpoint (Kubernetes service DNS name in RawDeployment mode)
DEFAULT_URL = "http://opt-125m-predictor/openai/v1/completions"
DEFAULT_MODEL = "opt-125m"
DEFAULT_DURATION = 600  # 10 minutes
DEFAULT_MAX_TOKENS = 200
DEFAULT_PROMPT = (
    "Write a long detailed story about a dragon who discovers a hidden kingdom"
)

# ---------------------------------------------------------------------------
# Globals for stats (used by load generation modes)
# ---------------------------------------------------------------------------
stats_lock = threading.Lock()
total_requests = 0
total_tokens = 0
total_errors = 0
start_time: float = 0.0
stop_event = threading.Event()


def send_request(url: str, model: str, prompt: str, max_tokens: int) -> dict | None:
    """Send a single completion request to the vLLM endpoint."""
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
    sleep_sec: float,
    stop: threading.Event,
):
    """Continuously send requests with a sleep between each."""
    global total_requests, total_tokens, total_errors

    while not stop.is_set():
        result = send_request(url, model, prompt, max_tokens)

        with stats_lock:
            if result and "usage" in result:
                total_requests += 1
                total_tokens += result["usage"].get("total_tokens", 0)
            else:
                total_errors += 1

        if sleep_sec > 0 and not stop.is_set():
            stop.wait(timeout=sleep_sec)


def print_stats():
    """Periodically print cumulative throughput stats (load generation modes)."""
    while not stop_event.is_set():
        stop_event.wait(timeout=10)
        if stop_event.is_set():
            break
        elapsed = time.time() - start_time
        with stats_lock:
            tok_rate = total_tokens / elapsed if elapsed > 0 else 0
            req_rate = total_requests / elapsed if elapsed > 0 else 0
            print(
                f"  [{elapsed:6.0f}s] requests={total_requests}  "
                f"tokens={total_tokens}  errors={total_errors}  "
                f"avg_tok/s={tok_rate:.1f}  avg_req/s={req_rate:.2f}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global start_time

    parser = argparse.ArgumentParser(
        description="Load generator for KServe + KEDA autoscaling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["stable-2", "stable-3", "custom"],
        default="stable-2",
        help="Mode to run (default: stable-2)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of concurrent workers (custom mode)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Sleep seconds between requests per worker (custom mode)",
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
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Duration in seconds for load modes (default: {DEFAULT_DURATION})",
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

    # ---------------------------------------------------------------------------
    # Load generation modes
    # ---------------------------------------------------------------------------
    if args.mode == "custom":
        if args.workers is None or args.sleep is None:
            parser.error("--workers and --sleep are required in custom mode")
        workers = args.workers
        sleep_sec = args.sleep
    else:
        preset = PRESETS[args.mode]
        workers = args.workers if args.workers is not None else preset["workers"]
        sleep_sec = args.sleep if args.sleep is not None else preset["sleep"]

    print("=== Load Generator ===")
    print(f"  Mode:       {args.mode}")
    print(f"  Workers:    {workers}")
    print(f"  Sleep:      {sleep_sec}s between requests")
    print(f"  URL:        {args.url}")
    print(f"  Model:      {args.model}")
    print(f"  Duration:   {args.duration}s")
    print(f"  Max tokens: {args.max_tokens}")
    print()
    print("Starting load... (Ctrl+C to stop)")
    print()

    def signal_handler(sig, frame):
        print("\n\nStopping load...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    start_time = time.time()

    stats_thread = threading.Thread(target=print_stats, daemon=True)
    stats_thread.start()

    threads = []
    for i in range(workers):
        t = threading.Thread(
            target=worker_loop,
            args=(
                args.url,
                args.model,
                args.prompt,
                args.max_tokens,
                sleep_sec,
                stop_event,
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        stop_event.wait(timeout=args.duration)
    except KeyboardInterrupt:
        pass

    stop_event.set()

    for t in threads:
        t.join(timeout=5)

    elapsed = time.time() - start_time
    with stats_lock:
        tok_rate = total_tokens / elapsed if elapsed > 0 else 0
        req_rate = total_requests / elapsed if elapsed > 0 else 0

    print()
    print("=== Final Stats ===")
    print(f"  Duration:   {elapsed:.1f}s")
    print(f"  Requests:   {total_requests}")
    print(f"  Tokens:     {total_tokens}")
    print(f"  Errors:     {total_errors}")
    print(f"  Avg tok/s:  {tok_rate:.1f}")
    print(f"  Avg req/s:  {req_rate:.2f}")


if __name__ == "__main__":
    main()
