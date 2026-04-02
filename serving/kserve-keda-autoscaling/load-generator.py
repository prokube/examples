#!/usr/bin/env python3
"""
Load generator for vLLM-based KServe InferenceService autoscaling demos.

Modes:

  stable-2   - Sustained moderate load (~8 tok/s) that scales to 2 replicas and holds
  stable-3   - Sustained heavy load (~22 tok/s) that scales to 3 replicas and holds
  custom     - Specify your own --workers and --sleep values
  calibrate  - Step through increasing concurrency levels and print a throughput/latency
               table. Use this to find the saturation point for your model and hardware,
               then set the KEDA threshold to ~80% of that value.

Usage (run from a notebook terminal inside the cluster):
    python load-generator.py --mode stable-2
    python load-generator.py --mode stable-3 --duration 300
    python load-generator.py --mode custom --workers 3 --sleep 1.0
    python load-generator.py --mode calibrate --url http://my-model-predictor/openai/v1/completions --model my-model

Press Ctrl+C to stop at any time.
"""

import argparse
import json
import math
import signal
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

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

# Default concurrency steps for calibrate mode (doubles each time)
DEFAULT_CALIBRATE_STEPS = [1, 2, 4, 8, 16]
DEFAULT_CALIBRATE_STEP_DURATION = 30  # seconds per concurrency level

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
    worker_id: int,
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    sleep_sec: float,
    local_stop: threading.Event | None = None,
):
    """Continuously send requests with a sleep between each.

    Stops when stop_event or local_stop (if given) is set.
    In load generation modes, updates the global stats counters.
    In calibrate mode, returns per-step counts via the return value of each
    call — but since this runs in a thread, results are collected via the
    shared calibrate_step_* counters instead.
    """
    global total_requests, total_tokens, total_errors

    stopper = local_stop if local_stop is not None else stop_event

    while not stopper.is_set() and not stop_event.is_set():
        result = send_request(url, model, prompt, max_tokens)

        with stats_lock:
            if result and "usage" in result:
                total_requests += 1
                total_tokens += result["usage"].get("total_tokens", 0)
            else:
                total_errors += 1

        if sleep_sec > 0 and not stopper.is_set():
            stopper.wait(timeout=sleep_sec)


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
# Calibrate mode helpers
# ---------------------------------------------------------------------------


def metrics_url_from_completions_url(completions_url: str) -> str:
    """Derive the /metrics URL from the completions endpoint URL.

    e.g. http://opt-125m-predictor/openai/v1/completions
      -> http://opt-125m-predictor/metrics
    """
    parsed = urlparse(completions_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/metrics"


def fetch_metrics(metrics_url: str) -> str:
    """Fetch the raw Prometheus metrics text from the vLLM endpoint."""
    try:
        with urllib.request.urlopen(metrics_url, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError):
        return ""


def parse_metric(metrics_text: str, prefix: str) -> float:
    """Extract the value of the first metric line starting with prefix."""
    for line in metrics_text.splitlines():
        if line.startswith(prefix) and not line.startswith("# "):
            try:
                return float(line.split()[-1])
            except ValueError:
                pass
    return 0.0


def snapshot_metrics(metrics_url: str) -> dict:
    """Return a snapshot of the counters needed for calibration."""
    text = fetch_metrics(metrics_url)
    return {
        "prompt_tokens": parse_metric(text, "vllm:prompt_tokens_total{"),
        "generation_tokens": parse_metric(text, "vllm:generation_tokens_total{"),
        "latency_count": parse_metric(text, "vllm:e2e_request_latency_seconds_count{"),
        "latency_sum": parse_metric(text, "vllm:e2e_request_latency_seconds_sum{"),
    }


def run_calibrate(args: argparse.Namespace) -> None:
    """Step through concurrency levels and print a throughput/latency table."""
    global total_requests, total_tokens, total_errors

    m_url = metrics_url_from_completions_url(args.url)

    steps = DEFAULT_CALIBRATE_STEPS
    step_duration = DEFAULT_CALIBRATE_STEP_DURATION

    print("=== vLLM single-replica throughput calibration ===")
    print(f"  URL:        {args.url}")
    print(f"  Model:      {args.model}")
    print(f"  Metrics:    {m_url}")
    print(f"  Duration:   {step_duration}s per concurrency step")
    print(f"  Max tokens: {args.max_tokens}")
    print()
    print("Make sure only ONE replica is running and there is no other traffic.")
    print("The ScaledObject (if deployed) should be deleted or paused first.")
    print()

    # Verify metrics are reachable
    test = fetch_metrics(m_url)
    if not test:
        print(f"ERROR: could not reach metrics endpoint at {m_url}")
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

    prev_rate: float = 0.0
    best_rate: float = 0.0  # last rate before a plateau was detected

    for concurrency in steps:
        # Snapshot before
        snap_before = snapshot_metrics(m_url)
        t0 = time.time()

        # Run load for step_duration seconds using a per-step stop event
        step_stop = threading.Event()
        threads = []
        # Reset per-step counters
        with stats_lock:
            total_requests = 0
            total_tokens = 0
            total_errors = 0

        for _ in range(concurrency):
            t = threading.Thread(
                target=worker_loop,
                args=(
                    0,
                    args.url,
                    args.model,
                    args.prompt,
                    args.max_tokens,
                    0.0,
                    step_stop,
                ),
                daemon=True,
            )
            t.start()
            threads.append(t)

        step_stop.wait(timeout=step_duration)
        step_stop.set()
        for t in threads:
            t.join(timeout=10)

        elapsed = time.time() - t0

        # Snapshot after (for latency delta only)
        snap_after = snapshot_metrics(m_url)

        # Throughput: derived from response bodies (exact), not /metrics counters.
        # The global total_tokens counter was reset at step start and incremented
        # by worker_loop for every completed request within this step.
        with stats_lock:
            step_tokens = total_tokens
            step_errors = total_errors
        rate = step_tokens / elapsed if elapsed > 0 else 0.0

        delta_count = snap_after["latency_count"] - snap_before["latency_count"]
        delta_sum = snap_after["latency_sum"] - snap_before["latency_sum"]
        mean_lat = f"{delta_sum / delta_count:.2f}" if delta_count > 0 else "n/a"

        # Flag plateau: throughput grew less than 15% despite adding concurrency
        note = ""
        plateau = prev_rate > 0 and (rate - prev_rate) / prev_rate < 0.15
        if plateau:
            note = "<-- plateau, saturation likely here"
        else:
            best_rate = rate  # still growing — update best

        err_note = f" ({step_errors} errors)" if step_errors else ""
        print(f"  {concurrency:<12} {rate:<22.1f} {mean_lat:<20} {note}{err_note}")
        prev_rate = rate

        # Stop early once clearly saturated
        if plateau and concurrency >= 4:
            break

    print()
    print("Find the last step where throughput was still growing.")
    print("Set your KEDA threshold to ~80% of its tok/s value.")
    print()
    threshold_suggestion = math.floor(best_rate * 0.8) if best_rate > 0 else "?"
    print(
        f"  Suggested threshold (80% of last pre-plateau rate): {threshold_suggestion} tok/s"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global start_time

    parser = argparse.ArgumentParser(
        description="Load generator and calibration tool for KServe + KEDA autoscaling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["stable-2", "stable-3", "custom", "calibrate"],
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
    # Calibrate mode — separate path, no global stat loop
    # ---------------------------------------------------------------------------
    if args.mode == "calibrate":
        signal.signal(
            signal.SIGINT, lambda s, f: (print("\nInterrupted."), stop_event.set())
        )
        run_calibrate(args)
        return

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
            args=(i, args.url, args.model, args.prompt, args.max_tokens, sleep_sec),
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
