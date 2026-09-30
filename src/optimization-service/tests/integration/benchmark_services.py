#!/usr/bin/env python3
"""Run baseline/current services in disposable containers on real complete logs."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import requests
import psutil

ROOT = Path(__file__).resolve().parents[4]
BASE = Path("/tmp/minersweeper-performance-20260930")
METRICS = ["fitness", "precision", "generalisation", "simplicity"]
LOGS = {
    "incidents": "BPI_Challenge_2013_incidents.xes",
    "financial": "BPI_Challenge_2012.xes",
    "sepsis": "Sepsis Cases - Event Log.xes",
    "hospital": "Hospital Billing - Event Log.xes",
}


def docker(*arguments):
    return subprocess.check_output(["docker", *arguments], text=True, stderr=subprocess.STDOUT).strip()


def http(base, path, payload=None, timeout=300):
    response = requests.get(base + path, timeout=timeout) if payload is None else requests.post(base + path, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "src/optimization-service/tests/integration/smoke_test_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Samples:
    """Process RSS and CPU from Linux procfs; sample every 200 ms."""
    def __init__(self, names):
        self.pids = {kind: int(docker("inspect", "--format", "{{.State.Pid}}", name)) for kind, name in names.items()}
        self.samples = []
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        while not self.stop.is_set():
            row = {"time": time.monotonic()}
            for kind, pid in self.pids.items():
                try:
                    root = psutil.Process(pid)
                    processes = [root, *root.children(recursive=True)]
                    rss, swap, cpu, threads = 0, 0, 0.0, 0
                    for process in processes:
                        try:
                            info = process.memory_info()
                            rss += info.rss
                            threads += process.num_threads()
                            cpu_times = process.cpu_times()
                            cpu += cpu_times.user + cpu_times.system
                            status = Path(f"/proc/{process.pid}/status").read_text()
                            match = re.search(r"^VmSwap:\s+(\d+)", status, re.M)
                            if match:
                                swap += int(match[1]) * 1024
                        except (psutil.Error, OSError):
                            pass
                    row[kind + "_VmRSS"] = rss
                    row[kind + "_VmSwap"] = swap
                    row[kind + "_cpu_seconds"] = cpu
                    row[kind + "_threads"] = threads
                except (OSError, ValueError, psutil.Error):
                    pass
            self.samples.append(row)
            self.stop.wait(.2)

    def summary(self, start, end):
        rows = [row for row in self.samples if start <= row["time"] <= end]
        result = {"sample_count": len(rows), "sample_period_seconds": .2, "scope": "sum of RSS and CPU of service root plus descendants; shared pages can be counted twice"}
        for kind in self.pids:
            for key in ("VmRSS", "VmSwap"):
                values = [row[kind + "_" + key] for row in rows if kind + "_" + key in row]
                result[kind + "_peak_sampled_" + key + "_bytes"] = max(values, default=0)
            result[kind + "_peak_threads"] = max((row.get(kind + "_threads", 0) for row in rows), default=0)
            values = [row[kind + "_cpu_seconds"] for row in rows if kind + "_cpu_seconds" in row]
            result[kind + "_cpu_seconds"] = values[-1] - values[0] if len(values) > 1 else 0
        return result

    def close(self):
        self.stop.set()
        self.worker.join(2)


def fixed_candidates():
    def miner(noise):
        return {"key": "inductive", "family": "inductive", "variant": "Inductive Miner - infrequent (IMf)", "parameters": {"noise_threshold": noise, "is_debug": False, "use_multithreading": False}}
    cases = [("imf_" + str(noise), {"preprocessings": [], "miner": miner(noise)}) for noise in (0., .2, .5)]
    cases.extend((name, {"preprocessings": [{"key": key, "method": "", "variant": "", "parameters": parameters}], "miner": miner(.2)}) for name, key, parameters in (
        ("matrix_imf", "matrix_filter", {"probability_of_removal_mf": .15, "subsequence_length_mf": 2}),
        ("variant_imf", "variant_filter", {"keep_threshold_vf": 80}),
        ("projection100_imf", "projection_filter", {"keep_threshold_p": 100}),
    ))
    return cases


def fixed_run(mining, filename, workers, sampler, smoke, directory, args):
    experiment = "fixed_" + uuid.uuid4().hex
    started = time.monotonic()
    aborted = threading.Event()
    def evaluate(case):
        if aborted.is_set():
            raise RuntimeError("fixed batch aborted")
        name, pipeline = case
        before = time.monotonic()
        request_id = uuid.uuid4().hex
        try:
            body = http(mining, "/pipeline", {"experiment_id": experiment, "request_id": request_id, "log_path": "/data/logs/" + filename, "pipeline": pipeline, "metrics": METRICS, "conformance_mode": "replay-token"}, timeout=args.fixed_timeout)
        except requests.RequestException:
            aborted.set()
            try:
                cancellation = http(mining, f"/experiments/{experiment}/evaluations/{request_id}/cancel", {}, timeout=5)
            except requests.RequestException as error:
                cancellation = {"error": str(error)}
            (directory / f"fixed-workers{workers}-{name}-timeout.json").write_text(json.dumps({"request_id": request_id, "experiment_id": experiment, "cancellation": cancellation}, indent=2))
            raise
        elapsed = time.monotonic() - before
        values = body.get("metrics") or {}
        if body.get("metrics_status") == "skipped_infeasible":
            if body.get("is_feasible") is not False or values:
                raise AssertionError("invalid omitted metrics")
        elif not all(isinstance(values.get(key), (int, float)) and 0 <= values[key] <= 1 for key in METRICS):
            raise AssertionError("invalid measured metrics")
        print(f"fixed workers={workers} case={name} elapsed={elapsed:.2f}s feasible={body.get('is_feasible')}", flush=True)
        return {"case": name, "pipeline": pipeline, "seconds": elapsed, "response": body}
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        cases = [case for case in fixed_candidates() if not (args.skip_hospital_zero_noise and filename == LOGS["hospital"] and case[0] == "imf_0.0")]
        futures = [pool.submit(evaluate, case) for case in cases]
        rows = [future.result() for future in as_completed(futures)]
    finally:
        aborted.set()
        pool.shutdown(wait=False, cancel_futures=True)
    ended = time.monotonic()
    artifacts = http(mining, "/artifacts/bulk", {"experiment_id": experiment, "evaluation_ids": [row["response"]["evaluation_id"] for row in rows], "include_pnml": True})
    spec = importlib.util.spec_from_file_location("probe", ROOT / "src/mining-service/src/test/python/probe_miners_v2.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    (directory / (f"fixed-workers{workers}-artifacts.json")).write_text(json.dumps(artifacts, indent=2))
    for artifact in artifacts["artifacts"]:
        probe.validate_artifact(artifact)
    http(mining, f"/experiments/{experiment}/cleanup", {})
    return {"workers": workers, "seconds": ended - started, "memory": sampler.summary(started, ended), "cases": rows, "artifact_validation": "PASS"}


def optimize(api, mining, filename, directory, sampler, args):
    destination = directory / "smoke.log"
    env = dict(os.environ, MINERSWEEPER_API_URL=api, MINERSWEEPER_MINING_URL=mining, SMOKE_XES=filename, SMOKE_N_WORKERS="4", SMOKE_MAX_EVALUATIONS=str(args.evaluations), SMOKE_POPULATION_SIZE="12", SMOKE_N_PARTITIONS="2", SMOKE_SEED="20260930", SMOKE_TIMEOUT_SECONDS=str(args.timeout), SMOKE_EXPORT_PATH=str(directory / "export.zip"), SMOKE_POLL_SECONDS="1")
    started = time.monotonic()
    with destination.open("w") as output:
        process = subprocess.Popen([sys.executable, str(ROOT / "src/optimization-service/tests/integration/smoke_test_v2.py")], env=env, stdout=output, stderr=subprocess.STDOUT)
        last = None
        while process.poll() is None:
            if time.monotonic() - started > args.timeout + 90:
                process.terminate()
                process.wait(10)
                break
            content = destination.read_text()
            lines = [line for line in content.splitlines() if line.startswith("status=")]
            if lines and lines[-1] != last:
                last = lines[-1]
                print(last, flush=True)
            time.sleep(2)
    ended = time.monotonic()
    content = destination.read_text()
    ids = re.findall(r"^job_id=(.+)$", content, re.M)
    result = {"seconds": ended - started, "returncode": process.returncode, "memory": sampler.summary(started, ended), "validator_output": content}
    if ids:
        result["job_id"] = ids[-1]
        result["job"] = http(api, "/optimizations/" + ids[-1])
        if result["job"].get("started_at") and result["job"].get("finished_at"):
            result["job_seconds"] = (datetime.fromisoformat(result["job"]["finished_at"]) - datetime.fromisoformat(result["job"]["started_at"])).total_seconds()
        if result["job"].get("status") == "completed":
            result["solutions"] = http(api, "/experiments/" + ids[-1] + "/solutions?scope=all")
            result["experiment"] = http(api, "/experiments/" + ids[-1])
    return result


def scenario(revision, log, args, output):
    key = revision + "-" + log
    directory = output / key
    directory.mkdir(parents=True, exist_ok=True)
    gc_directory = directory / "java"
    gc_directory.mkdir(exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    names = {"java": "msperf-java-" + suffix, "python": "msperf-python-" + suffix}
    source = ROOT if revision == "current" else args.baseline_source
    java_jar = source / "src/mining-service/target/prom-service-0.1.0.jar"
    if revision == "baseline" and args.baseline_java_jar:
        java_jar = args.baseline_java_jar
    # Java lazily loads classes. Never mount a build artifact that Maven may rewrite.
    frozen_jar = directory / "service-under-test.jar"
    shutil.copyfile(java_jar, frozen_jar)
    java_jar = frozen_jar
    heap_bytes = int(args.heap_gb * 1024**3)
    memory_bytes = int(args.memory_gb * 1024**3) if args.memory_gb else heap_bytes + 2 * 1024**3
    result = {"revision": revision, "log": LOGS[log], "java_jar_sha256": hashlib.sha256(java_jar.read_bytes()).hexdigest(), "heap_max_bytes": heap_bytes, "java_memory_limit_bytes": memory_bytes, "java_cpus": 4, "seed": 20260930, "evaluations": args.evaluations}
    sampler = None
    dump_timer = None
    started_names = []
    try:
        docker("run", "-d", "--pull=never", "--name", names["java"], "--network=host", "--memory=" + str(memory_bytes), "--memory-swap=" + str(memory_bytes), "--cpus=4", "-v", str(ROOT / "event_logs") + ":/data/logs:ro", "-v", str(java_jar) + ":/app/mining-service/target/prom-service-0.1.0.jar:ro", "-v", str(gc_directory) + ":/bench", "-e", "PORT=17070", "-e", "LOGS_ROOT=/data/logs", "-e", "PIPELINE_EVALUATOR_MODE=real", "-e", "PROM_TIMING_ENABLED=true", "-e", "PROM_TIMING_SLOW_MS=0", "-e", "PROM_VERBOSE_EXCEPTIONS=true", "-e", "PROM_LOG_TO_FILE=false", "-e", "PROM_MAX_CONCURRENT_EVALUATIONS=4", "-e", "PROM_ALLOW_MINER_MULTITHREADING=false", "-e", "JAVA_TOOL_OPTIONS=-Xms256m -Xmx" + str(heap_bytes // 1024**2) + "m -XX:+UseG1GC -XX:ActiveProcessorCount=4 -XX:+PrintGCDetails -XX:+PrintGCTimeStamps -Xloggc:/bench/gc.log", "rubjimjim/minersweeper-mining:develop")
        started_names.append(names["java"])
        docker("run", "-d", "--pull=never", "--name", names["python"], "--network=host", "--memory=1g", "--memory-swap=1g", "--cpus=1", "-v", str(source / "src/optimization-service") + ":/app/src/optimization-service:ro", "-v", str(ROOT / "event_logs") + ":/data/logs:ro", "-e", "JAVA_SERVICE_URL=http://127.0.0.1:17070", "-e", "OPT_DB_URL=sqlite:////tmp/benchmark.db", "-e", "LOGS_ROOT=/data/logs", "-e", "OPT_MAX_EVALUATION_WORKERS=4", "-e", "JAVA_SERVICE_TIMEOUT_SECONDS=300", "-e", "OPT_LOG_TO_FILE=false", "-e", "OPT_EVALUATION_TRACE_FILE=/tmp/evaluations.jsonl", "rubjimjim/minersweeper-optimization:develop", "gunicorn", "--bind", "0.0.0.0:17080", "--workers", "1", "--worker-class", "gthread", "--threads", "8", "--timeout", "600", "api:app")
        started_names.append(names["python"])
        mining, api = "http://127.0.0.1:17070", "http://127.0.0.1:17080"
        deadline = time.monotonic() + 60
        while True:
            try:
                http(mining, "/health", timeout=2)
                http(api, "/health", timeout=2)
                break
            except requests.RequestException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        sampler = Samples(names)
        if args.thread_dump_after:
            def dump_threads():
                try:
                    docker("kill", "--signal=QUIT", names["java"])
                except subprocess.CalledProcessError:
                    pass
            dump_timer = threading.Timer(args.thread_dump_after, dump_threads)
            dump_timer.start()
        smoke = load_smoke()
        result["fixed"] = []
        for workers in (() if args.only_optimization else (1, 4)):
            result["fixed"].append(fixed_run(mining, LOGS[log], workers, sampler, smoke, directory, args))
            (directory / "result.json").write_text(json.dumps(result, indent=2))
        print("OPTIMIZATION " + key, flush=True)
        result["optimization"] = optimize(api, mining, LOGS[log], directory, sampler, args)
    except Exception as error:
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()
        print("FAILED " + key + ": " + str(error), flush=True)
    finally:
        if dump_timer:
            dump_timer.cancel()
        if sampler is not None:
            sampler.close()
            (directory / "samples.json").write_text(json.dumps(sampler.samples))
        for name in reversed(started_names):
            kind = "java" if name == names["java"] else "python"
            try:
                result[kind + "_container_state"] = json.loads(docker("inspect", "--format", "{{json .State}}", name))
                (directory / (kind + ".log")).write_text(docker("logs", name))
                docker("stop", "-t", "10", name)
            finally:
                docker("rm", "-f", name)
        (directory / "result.json").write_text(json.dumps(result, indent=2))
    print("FINISHED " + key, flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", nargs="+", choices=list(LOGS), default=list(LOGS))
    parser.add_argument("--revisions", nargs="+", choices=["baseline", "current"], default=["baseline", "current"])
    parser.add_argument("--baseline-source", type=Path, default=BASE / "baseline",
                        help="Source tree for the baseline Python service")
    parser.add_argument("--baseline-java-jar", type=Path,
                        help="Override the baseline Java jar to isolate a particular Java change")
    parser.add_argument("--evaluations", type=int, default=72)
    parser.add_argument("--skip-hospital-zero-noise", action="store_true")
    parser.add_argument("--only-optimization", action="store_true")
    parser.add_argument("--fixed-timeout", type=int, default=300)
    parser.add_argument("--heap-gb", type=float, default=8.0)
    parser.add_argument("--memory-gb", type=float)
    parser.add_argument("--thread-dump-after", type=float)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", type=Path, default=BASE / "runs")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    failed = False
    for log in args.logs:
        for revision in args.revisions:
            result = scenario(revision, log, args, args.output)
            print(json.dumps({"log": log, "revision": revision, "error": result.get("error"), "optimization_seconds": result.get("optimization", {}).get("seconds"), "validation_returncode": result.get("optimization", {}).get("returncode")}), flush=True)
            failed |= bool(result.get("error")) or result.get("optimization", {}).get("returncode") != 0
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
