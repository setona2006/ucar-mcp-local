#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Usage:
  python invoke_ucar.py draw_fibo --args '{"mode":"quick","symbol":"GBPJPY","tf":"4h","x_ratio_start":0.25,"x_ratio_end":0.75,"headless":true,"outfile":"automation/screenshots/fibo.png"}'
  python invoke_ucar.py macro_quiettrap_report --args '{"symbol":"USDJPY","tf":"1h","preset_name":"senior_ma_cloud","draw_fibo":true,"fibo_mode":"quick","quiettrap":{"side":"sell","score":0.8},"outfile":"automation/screenshots/qt.png","headless":true}'
  # Reuse existing template + override a few fields
  python invoke_ucar.py draw_fibo --args '{"mode":"quick","symbol":"GBPJPY","tf":"4h","x_ratio_start":0.25,"x_ratio_end":0.75}' --overrides '{"outfile":"automation/screenshots/NEW.png"}'

  # On Windows PowerShell, prefer file-based args to avoid quoting issues:
  python invoke_ucar.py draw_fibo --args-file .\tmp_args.json --overrides-file .\tmp_overrides.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REQUESTS_DIR = Path("requests")
SERVER = [sys.executable, "mcp/mcp_server.py"]

# Keys to ignore when building the cache key (frequently changed or non-essential)
IGNORE_KEYS = {"outfile", "headless", "id", "timestamp"}

# Human-readable label fields to include in filename when present
PREFERRED_LABEL_FIELDS = [
    "symbol",
    "tf",
    "mode",
    "preset_name",
    "fibo_mode",
    "direction",
    "x_ratio_start",
    "x_ratio_end",
    "high",
    "low",
]


def _round_numbers(obj, ndigits: int = 6):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, list):
        return [_round_numbers(x, ndigits) for x in obj]
    if isinstance(obj, dict):
        return {k: _round_numbers(v, ndigits) for k, v in obj.items()}
    return obj


def _remove_ignored(d, ignore=IGNORE_KEYS):
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if k in ignore:
            continue
        if isinstance(v, dict):
            out[k] = _remove_ignored(v, ignore)
        elif isinstance(v, list):
            out[k] = [_remove_ignored(x, ignore) for x in v]
        else:
            out[k] = v
    return out


def _canonical_json(d) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def make_cache_key(tool: str, args: dict) -> str:
    """Make a stable, human-readable key + short hash for file naming."""
    norm = _remove_ignored(_round_numbers(args))
    parts = [tool]
    for f in PREFERRED_LABEL_FIELDS:
        if f in norm:
            parts.append(str(norm[f]))
    label = "_".join(str(p) for p in parts if p != "")
    h = hashlib.sha1(_canonical_json(norm).encode("utf-8")).hexdigest()[:8]
    return f"{label}__{h}"


def ensure_requests_dir(tool: str) -> Path:
    d = REQUESTS_DIR / tool
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_payload(tool: str, args: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": int(time.time()),
        "params": {"name": tool, "arguments": args},
    }


def run_server(payload: dict) -> int:
    payload_json = json.dumps(payload, ensure_ascii=False)
    proc = subprocess.run(
        SERVER,
        input=payload_json.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    sys.stdout.write(proc.stdout.decode("utf-8", errors="ignore"))
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", errors="ignore"))
    return proc.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "tool",
        help="tool name (e.g., draw_fibo, tune_indicator, macro_quiettrap_report)",
    )
    ap.add_argument("--args", help="JSON string for arguments")
    ap.add_argument("--args-file", help="Path to a JSON file for arguments")
    ap.add_argument("--overrides", help="JSON string to override arguments at run time")
    ap.add_argument(
        "--overrides-file", help="Path to a JSON file to override arguments at run time"
    )
    ap.add_argument(
        "--no-save", action="store_true", help="Do not save request template"
    )
    ns = ap.parse_args()

    if not ns.args and not ns.args_file:
        print("[ERROR] either --args or --args-file is required", file=sys.stderr)
        sys.exit(2)
    if ns.args and ns.args_file:
        print("[ERROR] specify only one of --args or --args-file", file=sys.stderr)
        sys.exit(2)

    try:
        if ns.args_file:
            txt = Path(ns.args_file).read_text(encoding="utf-8")
            base_args = json.loads(txt)
        else:
            base_args = json.loads(ns.args)
        if not isinstance(base_args, dict):
            raise ValueError("arguments must be a JSON object")
    except Exception as e:
        print(f"[ERROR] arguments JSON parse failed: {e}", file=sys.stderr)
        sys.exit(2)

    cache_key = make_cache_key(ns.tool, base_args)
    tool_dir = ensure_requests_dir(ns.tool)
    req_path = tool_dir / f"{cache_key}.json"

    payload = build_payload(ns.tool, base_args)

    if req_path.exists():
        try:
            payload = json.loads(req_path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupted template; will be overwritten below if saving
            pass
    else:
        if not ns.no_save:
            req_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"[cache] saved: {req_path}")

    # Apply overrides from string or file
    if ns.overrides and ns.overrides_file:
        print(
            "[ERROR] specify only one of --overrides or --overrides-file",
            file=sys.stderr,
        )
        sys.exit(2)
    if ns.overrides or ns.overrides_file:
        try:
            if ns.overrides_file:
                txt = Path(ns.overrides_file).read_text(encoding="utf-8")
                ov = json.loads(txt)
            else:
                ov = json.loads(ns.overrides)
            if not isinstance(ov, dict):
                raise ValueError("overrides must be a JSON object")
            payload.setdefault("params", {}).setdefault("arguments", {}).update(ov)
        except Exception as e:
            print(f"[ERROR] overrides JSON parse failed: {e}", file=sys.stderr)
            sys.exit(2)

    rc = run_server(payload)
    sys.exit(rc)


if __name__ == "__main__":
    main()
