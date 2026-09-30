#!/usr/bin/env python3
"""Keep compact, auditable measurements without embedding graphs or PNML."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re


def summarize(path):
    source = json.loads(path.read_text())
    result = {key: source[key] for key in ("revision", "log", "java_jar_sha256", "heap_max_bytes", "java_memory_limit_bytes", "java_cpus", "seed", "evaluations")}
    result["source_result"] = str(path)
    result["error"] = source.get("error")
    result["java_container_state"] = source.get("java_container_state")
    samples = path.parent / "samples.json"
    if samples.exists():
        rows = json.loads(samples.read_text())
        result["whole_scenario_memory"] = {"java_peak_sampled_RSS_bytes": max((row.get("java_VmRSS", 0) for row in rows), default=0), "java_peak_sampled_swap_bytes": max((row.get("java_VmSwap", 0) for row in rows), default=0)}
    logs = (path.parent / "java.log").read_text()
    if "[EVAL]" not in logs:
        logs = (path.parent.parent.parent / "runner.log").read_text()
    timings = []
    for line in logs.splitlines():
        if "event=evaluation_summary" in line:
            timings.append(dict(re.findall(r'(\w+)=("[^"]*"|\S+)', line)))
    result["fixed"] = []
    for batch in source.get("fixed", []):
        compact = {key: batch[key] for key in ("workers", "seconds", "memory", "artifact_validation")}
        compact["cases"] = []
        for case in batch["cases"]:
            response = case["response"]
            experiment = response["experiment_id"]
            suffix = response["evaluation_id"].rsplit("-", 1)[-1]
            matches = [t for t in timings if t.get("experiment_id") == experiment and t.get("trace_id", "").rsplit("-", 1)[-1] == suffix]
            compact["cases"].append({"case": case["case"], "seconds": case["seconds"], "metrics": response.get("metrics"), "metrics_status": response.get("metrics_status", "computed"), "feasible": response["is_feasible"], "timings_ms": {k: int(v) for t in matches for k, v in t.items() if k.endswith("_ms")}})
        result["fixed"].append(compact)
        if "scope" not in compact["memory"]:
            for key in list(compact["memory"]):
                if key.startswith("python_"):
                    del compact["memory"][key]
            compact["memory"]["scope"] = "Java process only; first-run Python sampler excluded gunicorn worker and is discarded"
    if "optimization" in source:
        optimization = source["optimization"]
        job = optimization.get("job", {})
        experiment_name = optimization.get("experiment", {}).get("experiment_name")
        actual = [t for t in timings if t.get("experiment_id") == experiment_name] if experiment_name else []
        solutions = optimization.get("solutions", {}).get("solutions", [])
        result["optimization"] = {"end_to_end_seconds": optimization["seconds"], "validator_returncode": optimization["returncode"], "memory": optimization["memory"], "job_status": job.get("status"), "job_error": job.get("error"), "counts": job.get("result_summary", {}).get("counts"), "job_id": optimization.get("job_id"), "physical_evaluations_with_summary": len(actual), "final_feasible_count": sum(s.get("is_feasible") is True for s in solutions), "final_computed_metrics_count": sum(s.get("metrics_status", "computed") == "computed" for s in solutions), "final_unique_fingerprints": len({s.get("fingerprint") for s in solutions}), "phase_summed_ms": {key: sum(int(t.get(key, 0)) for t in actual) for key in ("total_ms", "log_load_ms", "preprocess_ms", "discover_ms", "quality_ms", "metric_fitness_ms", "metric_precision_ms", "metric_generalisation_ms", "metric_simplicity_ms", "store_artifact_ms")}}
        if job.get("started_at") and job.get("finished_at"):
            result["optimization"]["job_seconds"] = (datetime.fromisoformat(job["finished_at"]) - datetime.fromisoformat(job["started_at"])).total_seconds()
        if "scope" not in result["optimization"]["memory"]:
            for key in list(result["optimization"]["memory"]):
                if key.startswith("python_"):
                    del result["optimization"]["memory"][key]
            result["optimization"]["memory"]["scope"] = "Java process only; first-run Python sampler excluded gunicorn worker and is discarded"
    gc = path.parent / "java/gc.log"
    if gc.exists():
        pauses = [float(v) for v in re.findall(r'\[GC pause[^\n]*, ([0-9.]+) secs\]', gc.read_text())]
        full = [float(v) for v in re.findall(r'\[Full GC[^\n]*, ([0-9.]+) secs\]', gc.read_text())]
        result["gc_whole_scenario"] = {"pause_count": len(pauses), "pause_seconds": sum(pauses), "full_gc_count": len(full), "full_gc_seconds": sum(full), "scope": "whole JVM lifetime including fixed batches; concurrent GC excluded"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [summarize(path) for directory in args.directories for path in sorted(directory.glob("*/result.json"))]
    args.output.write_text(json.dumps({"baseline_commit": "de3d395", "results": rows}, indent=2) + "\n")
    for row in rows:
        opt = row.get("optimization", {})
        print(row["heap_max_bytes"] // 2**30, row["revision"], row["log"], "seconds=", opt.get("job_seconds"), "RSS MiB=", round(opt.get("memory", {}).get("java_peak_sampled_VmRSS_bytes", 0) / 2**20), "error=", row.get("error"))


if __name__ == "__main__":
    main()
