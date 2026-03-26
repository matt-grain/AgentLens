"""
Automated mailbox brain — polls for pending requests and submits responses.

Usage:
    # Terminal 1: Start proxy in mailbox mode
    uv run agentlens serve --mode mailbox

    # Terminal 2: Start this brain
    uv run python examples/mailbox_brain/brain.py

    # Terminal 3: Send requests (or run CrewAI agent)
    curl -X POST http://localhost:8650/v1/chat/completions ...
"""

import argparse
import sys
import time

import httpx


def _last_user(messages: list[dict]) -> str:
    return next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "(no user message)",
    )


def check_health(client: httpx.Client, url: str) -> None:
    try:
        client.get(f"{url}/health", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"[Brain] Proxy not reachable at {url}: {exc}", file=sys.stderr)
        print("[Brain] Start it with: uv run agentlens serve --mode mailbox", file=sys.stderr)
        sys.exit(1)


def poll_once(client: httpx.Client, url: str, verbose: bool) -> int:
    """Poll the mailbox once. Returns the number of requests handled."""
    pending = client.get(f"{url}/mailbox", timeout=10).raise_for_status().json()
    if not pending:
        return 0

    for entry in pending:
        req_id = entry["id"]
        detail = client.get(f"{url}/mailbox/{req_id}", timeout=10).raise_for_status().json()
        messages = detail.get("messages", [])

        if verbose:
            print(f"[Brain] Request #{req_id} messages: {messages}")

        last = _last_user(messages)
        preview = last[:60] + ("…" if len(last) > 60 else "")
        response_text = f"Based on my analysis: {last}"

        client.post(
            f"{url}/mailbox/{req_id}",
            json={"response": response_text},
            timeout=10,
        ).raise_for_status()

        print(f"[Brain] Request #{req_id}: {preview!r} → responded")

    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentLens mailbox brain")
    parser.add_argument("--url", default="http://localhost:8650", help="Proxy base URL")
    parser.add_argument("--idle-timeout", type=int, default=30, help="Seconds idle before exit")
    parser.add_argument("--verbose", action="store_true", help="Print full request details")
    args = parser.parse_args()

    idle_seconds = 0
    with httpx.Client() as client:
        check_health(client, args.url)
        print(f"[Brain] Connected to {args.url}. Polling (idle timeout: {args.idle_timeout}s)…")

        while True:
            try:
                handled = poll_once(client, args.url, args.verbose)
            except httpx.HTTPError as exc:
                print(f"[Brain] HTTP error: {exc}", file=sys.stderr)
                handled = 0

            idle_seconds = 0 if handled else idle_seconds + 1
            if idle_seconds >= args.idle_timeout:
                print(f"[Brain] No requests for {args.idle_timeout}s — exiting.")
                break

            time.sleep(1)


if __name__ == "__main__":
    main()
