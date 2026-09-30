#!/usr/bin/env python3
"""Probe real client timeout/cancellation in a disposable, warmed ProM JVM."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import uuid

import requests

from benchmark_services import ROOT, LOGS, METRICS, Samples, docker, http, fixed_candidates

sys.path.insert(0, str(ROOT / "src/optimization-service/src"))
from java_service_client import ProMServiceClient
from execution_control import EvaluationTerminationUnconfirmed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", choices=list(LOGS), default="hospital")
    parser.add_argument("--heap-gb", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    name = "msperf-cancel-" + uuid.uuid4().hex[:10]
    experiment = "cancellation_" + uuid.uuid4().hex
    base = "http://127.0.0.1:17070"
    result = {"log": LOGS[args.log], "heap_gb": args.heap_gb, "http_timeout_seconds": args.timeout}
    sampler = None
    started = False
    try:
        docker("run", "-d", "--pull=never", "--name", name, "--network=host",
               f"--memory={args.heap_gb + 2}g", f"--memory-swap={args.heap_gb + 2}g", "--cpus=4",
               "-v", str(ROOT / "event_logs") + ":/data/logs:ro",
               "-v", str(ROOT / "src/mining-service/target/prom-service-0.1.0.jar") + ":/app/mining-service/target/prom-service-0.1.0.jar:ro",
               "-e", "PORT=17070", "-e", "LOGS_ROOT=/data/logs", "-e", "PIPELINE_EVALUATOR_MODE=real",
               "-e", "PROM_TIMING_ENABLED=true", "-e", "PROM_TIMING_SLOW_MS=0", "-e", "PROM_LOG_TO_FILE=false",
               "-e", f"JAVA_TOOL_OPTIONS=-Xms256m -Xmx{args.heap_gb}g -XX:+UseG1GC -XX:ActiveProcessorCount=4",
               "rubjimjim/minersweeper-mining:develop")
        started = True
        deadline = time.monotonic() + 60
        while True:
            try:
                http(base, "/health", timeout=2)
                break
            except requests.RequestException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        sampler = Samples({"java": name})
        client = ProMServiceClient(base, timeout_seconds=300, experiment_id=experiment)
        warmup_pipeline = fixed_candidates()[-1][1]
        warmup_pipeline["preprocessings"][0]["parameters"]["keep_threshold_p"] = 1
        result["warmup_pipeline"] = warmup_pipeline
        result["warmup"] = client.evaluate_pipeline("/data/logs/" + LOGS[args.log], warmup_pipeline, METRICS)
        client.timeout_seconds = args.timeout
        original_post = requests.post
        dispatched = []

        def recorded_post(url, **kwargs):
            if url.endswith("/pipeline"):
                dispatched.append(kwargs["json"])
            return original_post(url, **kwargs)

        before = time.monotonic()
        try:
            with patch("java_service_client.requests.post", side_effect=recorded_post):
                result["response"] = client.evaluate_pipeline("/data/logs/" + LOGS[args.log], fixed_candidates()[0][1], METRICS)
            result["outcome"] = "completed_before_timeout"
        except EvaluationTerminationUnconfirmed as error:
            result["outcome"] = "termination_unconfirmed"
            result["error"] = str(error)
        except requests.Timeout as error:
            result["outcome"] = "timeout_termination_confirmed"
            result["error"] = str(error)
        result["client_elapsed_seconds"] = time.monotonic() - before
        result["dispatched_after_warmup"] = len(dispatched)
        request_id = dispatched[0]["request_id"]
        result["request_id"] = request_id
        path = f"/experiments/{experiment}/evaluations/{request_id}/status"
        result["status_immediately"] = http(base, path, timeout=5)
        time.sleep(2)
        result["status_after_two_seconds"] = http(base, path, timeout=5)
        result["health_after_timeout"] = http(base, "/health", timeout=5)
        if result["outcome"] == "termination_unconfirmed":
            docker("kill", "--signal=QUIT", name)
            time.sleep(2)
        else:
            result["cleanup"] = http(base, f"/experiments/{experiment}/cleanup", {}, timeout=10)
    except Exception as error:
        result["probe_error"] = str(error)
        raise
    finally:
        if sampler:
            sampler.close()
            (args.output / "samples.json").write_text(json.dumps(sampler.samples))
        if started:
            (args.output / "java.log").write_text(docker("logs", name))
            docker("stop", "-t", "5", name)
            result["container_state_after_stop"] = json.loads(docker("inspect", "--format", "{{json .State}}", name))
            docker("rm", name)
        (args.output / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
