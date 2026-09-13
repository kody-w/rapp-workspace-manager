#!/usr/bin/env python3
"""Combine canonical RAPP checks with nonempty canonical project-chain evidence."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import workspace_manager as manager


def load_tool(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("canonical verification tool unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_repository(root, rapp1_path):
    root = Path(root).absolute()
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        reference = manager.load_rapp(rapp1_path)
        checker = load_tool("manager_canonical_checker", Path(rapp1_path) / "rapp_check.py")
        verdict, findings, evidence = checker.check_repo(str(root))
        writer = load_tool("manager_canonical_chain_verifier", Path(__file__).parent / "append_frame.py")
        writer.ROOT = str(root)
        writer.rapp = reference
        frame_count = stream_count = 0
        for slug in writer.all_slugs():
            try:
                chain = writer.verify_chain(slug)
            except (SystemExit, OSError, ValueError, KeyError) as error:
                findings.append({
                    "artifact": f"projects/{slug}/frames", "rule": "canonical-chain",
                    "detail": str(error),
                })
                continue
            if chain:
                stream_count += 1
                frame_count += len(chain)
                evidence.append({
                    "artifact": f"projects/{slug}/frames",
                    "ok": f"{len(chain)} existing frames verified by canonical rapp.verify_frame through append_frame.verify_chain",
                })
        if frame_count == 0:
            findings.append({
                "artifact": "projects/*/frames", "rule": "nonzero-frame-evidence",
                "detail": "Refusing a zero-frame conformance claim.",
            })
        return {
            "repo": str(root),
            "verdict": "DRIFT" if findings or verdict == "DRIFT" else "COMPLIANT",
            "findings": findings, "evidence": evidence,
            "frames_verified": frame_count, "streams_verified": stream_count,
        }
    finally:
        sys.dont_write_bytecode = previous_bytecode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--rapp1-path")
    args = parser.parse_args()
    result = check_repository(args.repo, manager.find_rapp1(args.rapp1_path))
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(int(result["verdict"] != "COMPLIANT"))
