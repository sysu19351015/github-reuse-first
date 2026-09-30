#!/usr/bin/env python3
"""GitHub reuse workflow CLI: search, inspect, report, acquire and validate."""
import argparse
import json
import os
import sys
from reuse_common import (GitHub, ReuseError, SafeRedirect, VERSION, digest,
                          normalize_repo, read_json, safe_path, write_json)
from reuse_discovery import search, inspect_repo
from reuse_acquisition import acquire, validate_review, extract_archive, audit_source, validate_record
from reuse_reporting import render_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--token-env", default="GITHUB_TOKEN", help="Read token from this environment variable only")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search", help="Search public GitHub repositories")
    p.add_argument("--query", action="append", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--pages", type=int, default=1)
    p = sub.add_parser("inspect", help="Fetch immutable evidence and a license-review draft")
    p.add_argument("--repo", required=True)
    p.add_argument("--ref")
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--out", required=True)
    p = sub.add_parser("report", help="Render evidence-based Codex/human assessment")
    p.add_argument("--assessment", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("acquire", help="Acquire reviewed source without executing third-party code")
    p.add_argument("--inspection", required=True)
    p.add_argument("--review", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--report-dir", required=True)
    p.add_argument("--method", choices=["archive", "git"], default="archive")
    p = sub.add_parser("validate", help="Validate source-record invariants")
    p.add_argument("--record", required=True)
    args = parser.parse_args(argv)
    try:
        client = GitHub(os.environ.get(args.token_env))
        if args.command == "search":
            result = search(client, args.query, args.out, args.limit, args.pages)
            print(json.dumps({"status": result["status"], "candidates": len(result["candidates"]),
                              "out": args.out}, ensure_ascii=False))
            return 2 if result["errors"] else 0
        if args.command == "inspect":
            result = inspect_repo(client, args.repo, args.ref, args.out, args.file)
            print(json.dumps({"commit": result["resolved_commit"], "evidence_files": len(result["evidence"]),
                              "warnings": result["warnings"], "out": args.out}, ensure_ascii=False))
            return 0
        if args.command == "report":
            result = render_report(args.assessment, args.out)
        elif args.command == "acquire":
            result = acquire(client, args.inspection, args.review, args.dest, args.report_dir, args.method)
            print(json.dumps({"status": result["status"], "report_dir": args.report_dir}, ensure_ascii=False))
            return 3 if result["status"] == "partial" else 0
        else:
            validate_record(read_json(args.record))
            result = {"valid": True}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ReuseError, OSError, KeyError, TypeError, ValueError) as exc:
        # Do not emit raw HTTP bodies, tokens, command output or tracebacks.
        print("Error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
