#!/usr/bin/env python3
"""Compare full seeded trajectories against a temporary native ProM service.

Compile mining-service first. Defaults to a tiny generated XES; --log accepts
an existing log. Writes evidence in --output and always stops its own JVM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import requests
import psutil

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src/optimization-service/src"))
from api.manager_runtime import execute_job
from execution_control import ExecutionControl
from java_service_client import ProMServiceClient


def scientific_state(result):
    keys = ("logical_attempt_id", "variables", "pipeline", "objectives", "constraints",
            "metrics", "is_feasible", "constraint_violations", "model_semantic_sha256", "discovery_metadata")
    def population(solutions):
        return [{key: solution.get(key) for key in keys} for solution in solutions]
    return {"final": population(result["all_solutions"]),
            "pareto": population(result["pareto_solutions"]),
            "snapshots": [{"evaluations_done": s["evaluations_done"], "solutions": population(s["solutions"])}
                          for s in result["population_snapshots"]]}


def evaluated_state(path):
    """Include rejected offspring, which never appear in population snapshots."""
    keys = ("metrics", "constraints", "constraint_violations", "is_feasible",
            "model_semantic_sha256", "metrics_status", "discovery_metadata")
    rows = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        key = json.dumps(row["pipeline"], sort_keys=True, separators=(",", ":"))
        payload = row.get("response", {})
        rows[key] = {name: payload.get(name) for name in keys}
        if "error" in row: rows[key]["error"] = row["error"]
    return rows


class ProcessSamples:
    """RSS/CPU/swap and system memory every 200 ms; no forced GC."""
    def __init__(self, pid):
        self.process = psutil.Process(pid)
        self.rows = []
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopped.is_set():
            try:
                status = Path(f"/proc/{self.process.pid}/status").read_text()
                swap = next((int(line.split()[1])*1024 for line in status.splitlines() if line.startswith("VmSwap:")), 0)
                cpu = self.process.cpu_times()
                self.rows.append({"time": time.monotonic(), "rss": self.process.memory_info().rss,
                                  "cpu_seconds": cpu.user+cpu.system, "swap": swap,
                                  "system_available": psutil.virtual_memory().available})
            except (OSError, psutil.Error):
                break
            self.stopped.wait(.2)

    def close(self):
        self.stopped.set(); self.thread.join(2)

    def summary(self, start, end):
        rows = [r for r in self.rows if start <= r["time"] <= end]
        return {"sample_period_seconds": .2, "sample_count": len(rows),
                "java_peak_rss_bytes": max((r["rss"] for r in rows), default=0),
                "java_peak_swap_bytes": max((r["swap"] for r in rows), default=0),
                "system_min_available_bytes": min((r["system_available"] for r in rows), default=0),
                "java_cpu_seconds": rows[-1]["cpu_seconds"]-rows[0]["cpu_seconds"] if len(rows)>1 else 0}


def start_service(args, output):
    home = ROOT / "tools/prom-lite-1.4-all-platforms"
    jars = sorted(p for directory in (home / "lib", home / "packages") for p in directory.rglob("*.jar")
                  if p.name != "split-miner-1.7.1-all.jar")
    native = sorted({str(p.parent) for p in home.rglob("*.so")})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(PORT=str(port), LOGS_ROOT=str(output), ARTIFACTS_ROOT=str(output / "artifacts"),
               LD_LIBRARY_PATH=os.pathsep.join(native), PROM_ALLOW_MINER_MULTITHREADING="false",
               PROM_MAX_CONCURRENT_EVALUATIONS=str(args.admission_workers), PROM_TIMING_ENABLED="true")
    classpath = os.pathsep.join([str(args.service_classes),
                               str(ROOT / "src/mining-service/target/dependency/*"), *map(str, jars)])
    handle = (output / "service.log").open("w")
    process = subprocess.Popen([args.java, f"-Xmx{args.heap_gb}g", "-XX:+UseG1GC",
                                "-Xloggc:"+str(output / "gc.log"), "-XX:+PrintGCDetails", "-XX:+PrintGCDateStamps",
                                "-Djava.awt.headless=true",
                                "-Djava.library.path=" + os.pathsep.join(native), "-cp", classpath,
                                "com.minersweeper.javaservice.app.PromService"], env=env, cwd=ROOT,
                               stdout=handle, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and process.poll() is None:
            try:
                if requests.get(url + "/health", timeout=1).ok:
                    return process, handle, url
            except requests.RequestException:
                pass
            time.sleep(.1)
        raise RuntimeError("Temporary service did not start: " + str(output / "service.log"))
    except BaseException:
        process.terminate(); process.wait(timeout=10); handle.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population-size", type=int, default=12)
    parser.add_argument("--max-evaluations", type=int, default=120)
    parser.add_argument("--java", default="/usr/lib/jvm/java-8-openjdk-amd64/bin/java")
    parser.add_argument("--heap-gb", type=int, default=8)
    parser.add_argument("--workers", default="1,4,4")
    parser.add_argument("--fresh-jvm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--admission-workers", type=int, default=4)
    parser.add_argument("--service-classes", type=Path, default=ROOT / "src/mining-service/target/classes")
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    log = args.log.resolve() if args.log else output / "reproducibility.xes"
    if args.log is None:
        traces = ["SABCE", "SACBE", "SBACE", "SBCAE", "SACE", "SABE", "SABCE", "SACBE"]
        content = '<?xml version="1.0"?><log xes.version="1.0" xmlns="http://www.xes-standard.org/">'
        for trace in traces:
            content += "<trace>" + "".join(f'<event><string key="concept:name" value="{a}"/></event>' for a in trace) + "</trace>"
        log.write_text(content + "</log>")
    logging.disable(logging.CRITICAL)
    os.environ["OPT_MAX_EVALUATION_WORKERS"] = str(max(map(int, args.workers.split(','))))
    process = handle = samples = None
    report = {"heap_gb": args.heap_gb, "log": str(log), "fresh_jvm": args.fresh_jvm, "runs": []}
    baseline = None
    baseline_evaluations = None
    baseline_build = None
    try:
        for repetition, workers in enumerate(map(int, args.workers.split(','))):
            run_directory = output / f"run-{repetition}"; run_directory.mkdir(exist_ok=True)
            if process is None:
                process, handle, url = start_service(args, run_directory)
                samples = ProcessSamples(process.pid)
            os.environ["OPT_EVALUATION_TRACE_FILE"] = str(run_directory / "evaluations.jsonl")
            # Perturb ambient states on purpose; private streams must ignore them.
            random.seed(100 + repetition); np.random.seed(900 + repetition)
            control = ExecutionControl(); job_id = f"repro-{repetition}"
            manager = SimpleNamespace(_lock=threading.Lock(), _subscribers={}, java_service_timeout_seconds=args.timeout_seconds,
                _jobs={job_id: {"job_id": job_id, "status": "running", "_control": control,
                               "progress": {"evaluations_done": 0, "max_evaluations": args.max_evaluations}}})
            config = {"execution_name": job_id, "log_path": str(log), "service_url": url,
                "metrics": ["fitness", "precision", "simplicity", "generalisation"],
                "excluded_miners": ["ilp", "hybrid_ilp"], "conformance_mode": "replay-token",
                "discover": {"seed": args.seed, "population_size": args.population_size,
                             "max_evaluations": args.max_evaluations, "n_partitions": 2, "n_workers": workers}}
            started = time.monotonic()
            original_evaluate = ProMServiceClient.evaluate_pipeline
            corpus_lock = threading.Lock()
            def recorded_evaluate(client, log_path, pipeline, metrics, **kwargs):
                row = {"log_path": log_path, "pipeline": pipeline, "metrics": metrics}
                try:
                    response = original_evaluate(client, log_path, pipeline, metrics, **kwargs)
                    row["response"] = response
                    return response
                except BaseException as error:
                    row["error"] = str(error)
                    raise
                finally:
                    with corpus_lock:
                        with (run_directory / "corpus.jsonl").open("a") as corpus:
                            corpus.write(json.dumps(row, sort_keys=True)+"\n")
            try:
                with patch.object(ProMServiceClient, 'evaluate_pipeline', recorded_evaluate):
                    result = execute_job(manager, job_id, config)
            except BaseException as error:
                ended = time.monotonic()
                report["runs"].append({"workers": workers, "seconds": ended-started,
                                      "status": "failed", "error": str(error), "error_type": type(error).__name__,
                                      "traceback": traceback.format_exc(), "resources": samples.summary(started, ended)})
                (output / "report.json").write_text(json.dumps(report, indent=2))
                raise
            state = scientific_state(result)
            build = {"log_sha256": result["log_sha256"],
                     "optimizer_source_sha256": result["optimizer_source_sha256"],
                     "evaluation_environments": result["optimizer_config"].get("evaluation_environments"),
                     "evaluation_policy_versions": result["optimizer_config"].get("evaluation_policy_versions")}
            if baseline_build is None: baseline_build = build
            if build != baseline_build:
                raise AssertionError("Build, environment or log changed between repetitions")
            evaluations = evaluated_state(run_directory / "corpus.jsonl")
            if baseline_evaluations is None: baseline_evaluations = evaluations
            evaluation_digest = hashlib.sha256(json.dumps(evaluations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            digest = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (output / f"state-{repetition}.json").write_text(json.dumps(state, indent=2))
            if baseline is None: baseline = state
            report["runs"].append({"workers": workers, "seconds": time.monotonic() - started,
                "status": "completed", "resources": samples.summary(started, time.monotonic()),
                "trajectory_sha256": digest, "matches_reference": state == baseline,
                "evaluations_sha256": evaluation_digest, "evaluations_match_reference": evaluations == baseline_evaluations,
                "log_sha256": result["log_sha256"], "optimizer_source_sha256": result["optimizer_source_sha256"],
                "counts": result["counts"], "optimizer_config": result["optimizer_config"]})
            (output / "report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps({key: value for key, value in report["runs"][-1].items()
                              if key != "optimizer_config"}), flush=True)
            if state != baseline: raise AssertionError("Seeded scientific trajectory differs")
            if result["optimizer_config"]["reproducibility_status"] != "controlled":
                raise AssertionError("Run contains errors, incompatible policies or untracked environment")
            if not result["counts"]["pareto_solutions"]: raise AssertionError("No feasible Pareto solution tested")
            (run_directory / "samples.json").write_text(json.dumps(samples.rows))
            if args.fresh_jvm:
                process.terminate(); process.wait(timeout=10); handle.close(); samples.close()
                process = handle = samples = None
    finally:
        if process is not None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            handle.close(); samples.close()
    if not all(run["evaluations_match_reference"] for run in report["runs"]):
        raise AssertionError("Evaluations differ, including rejected offspring; see corpus.jsonl")
    print("PASS: all evaluations, full trajectory and final Pareto match for requested workers")


if __name__ == "__main__": main()
