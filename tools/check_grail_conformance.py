#!/usr/bin/env python3
"""Run the candidate's exact safe tests in an owned mirror; never write to the supplied checkout."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import grail_runtime as runtime
from grail_runtime import encode, explicit_path, require, sha
from routing_io import RoutingError, atomic_text, directory_fd


def check(checkout, rapp1_path, output):
    checkout, rapp1_path = explicit_path(checkout), explicit_path(rapp1_path)
    output = Path(output)
    require(not output.is_absolute() and ".." not in output.parts and output != Path("."),
            "grail-conformance-relative-owned-output-required")
    destination = Path.cwd() / output
    require(not destination.exists(), "grail-conformance-use-fresh-output")
    require(not destination.is_relative_to(checkout), "grail-candidate-checkout-is-read-only")
    before = runtime.capture_checkout(checkout)
    image = runtime.Runtime(checkout, rapp1_path, before)
    image.close()
    mirror = destination / "public-candidate"
    for name, raw in before.items():
        target = mirror / name
        with directory_fd(target.parent, create=True):
            pass
        atomic_text(target, raw.decode("utf-8"))
    require(runtime.capture_checkout(mirror) == before, "grail-validation-mirror-substitution")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONSTARTUP", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["RAPP1_PATH"] = str(rapp1_path)
    command = [
        sys.executable, "-B", str(mirror / runtime.PROTOCOL / "reference/conformance.py"),
        "--rapp1-path", str(rapp1_path), "--output", ".validation/blocking-gates",
    ]
    completed = subprocess.run(command, cwd=mirror, env=env, capture_output=True, text=True, timeout=600)
    atomic_text(destination / "protocol-stdout.log", completed.stdout)
    atomic_text(destination / "protocol-stderr.log", completed.stderr)
    require(completed.returncode == 0, "grail-canonical-blocking-conformance-failed-see-owned-log")
    result = json.loads((mirror / ".validation/blocking-gates/conformance-results.json").read_bytes())
    require(result["tests_run"] > 0 and result["failures"] == result["errors"] == result["skipped"] == 0
            and result["rapp_frames_verified"] > 0, "grail-zero-or-failed-conformance")
    require(runtime.capture_checkout(checkout) == before, "grail-candidate-changed-during-conformance")
    report = {
        **runtime.contract(), "canonical_tests": result["tests_run"],
        "canonical_frames_verified": result["rapp_frames_verified"],
        "failures": 0, "errors": 0, "skipped": 0,
        "candidate_bytes_unchanged": True, "exact_public_mirror_only": True,
        "closure_checksums": {name: sha(raw) for name, raw in sorted(before.items())},
        "protocol_result": result, "signed_grail_activation": False,
    }
    atomic_text(destination / "conformance-results.json", encode(report).decode("ascii"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-checkout", required=True)
    parser.add_argument("--rapp1-path", required=True)
    parser.add_argument("--output", default=".validation/grail-cross-conformance")
    args = parser.parse_args()
    try:
        result = check(args.protocol_checkout, args.rapp1_path, args.output)
        print(json.dumps({key: value for key, value in result.items()
                          if key not in ("closure_checksums", "protocol_result")}, sort_keys=True))
        return 0
    except (OSError, ValueError, RoutingError, subprocess.SubprocessError) as error:
        print("REFUSED: " + json.dumps(str(error), ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
