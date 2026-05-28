#!/usr/bin/env python3
"""
centaurXiv Knowledge Graph API smoke tester.

stdlib-only, read-only, byte-capped. Safe for agent runners.
Based on Lumen's test design (loop 1913).

Usage:
    python3 smoke-test.py
    python3 smoke-test.py --base https://api.centaurxiv.org
    python3 smoke-test.py --endpoint /crossings?format=json --endpoint /search/fidelity?format=json
    python3 smoke-test.py --strict-warnings
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

DEFAULT_BASE = "https://api.centaurxiv.org"
MAX_BYTES = 512_000
TIMEOUT = 15

DEFAULT_ENDPOINTS = [
    ("/?format=json", "home"),
    ("/help?format=json", "help"),
    ("/crossings?format=json", "crossings"),
    ("/search/fidelity?format=json", "search"),
    ("/edges/constrains?format=json", "edges"),
]


def check(base, path, label, max_bytes, timeout):
    url = base.rstrip("/") + path
    warnings = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "centaurxiv-smoke-test/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            body = resp.read(max_bytes + 1)
            truncated = len(body) > max_bytes
            if truncated:
                body = body[:max_bytes]
                warnings.append(f"truncated at {max_bytes} bytes")
            if "json" not in ct:
                warnings.append(f"content-type: {ct}")
            data = json.loads(body)
            if isinstance(data, dict):
                keys = list(data.keys())[:5]
            elif isinstance(data, list):
                keys = [f"[{len(data)} items]"]
            else:
                keys = [str(type(data))]
            return True, warnings, keys
    except urllib.error.HTTPError as e:
        return False, [f"HTTP {e.code}"], []
    except json.JSONDecodeError:
        return False, ["invalid JSON"], []
    except Exception as e:
        return False, [str(e)], []


def main():
    parser = argparse.ArgumentParser(description="centaurXiv KG API smoke tester")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--endpoint", action="append", dest="endpoints")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--strict-warnings", action="store_true")
    args = parser.parse_args()

    if args.endpoints:
        checks = [(ep, ep.split("?")[0].strip("/") or "home") for ep in args.endpoints]
    else:
        checks = DEFAULT_ENDPOINTS

    passed = 0
    failed = 0
    warned = 0

    for path, label in checks:
        ok, warns, keys = check(args.base, path, label, args.max_bytes, args.timeout)
        status = "PASS" if ok else "FAIL"
        if ok and warns:
            status = "FAIL" if args.strict_warnings else "WARN"
        if status == "FAIL":
            failed += 1
        elif status == "WARN":
            warned += 1
        else:
            passed += 1
        detail = f" ({', '.join(warns)})" if warns else ""
        key_info = f" keys={keys}" if ok else ""
        print(f"  [{status}] {label:<12} {path}{detail}{key_info}")

    print(f"\n{passed} passed, {warned} warnings, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
