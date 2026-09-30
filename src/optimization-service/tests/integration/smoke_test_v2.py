#!/usr/bin/env python3
"""Run and validate a small MineSweeper schema-v3 experiment through public APIs."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


API_URL = os.environ.get("MINERSWEEPER_API_URL", "http://localhost:8080").rstrip("/")
MINING_URL = os.environ.get("MINERSWEEPER_MINING_URL", "http://localhost:7070").rstrip("/")
XES_LOG = os.environ.get("SMOKE_XES", "BPI_Challenge_2013_open_problems.xes")
TIMEOUT_SECONDS = int(os.environ.get("SMOKE_TIMEOUT_SECONDS", "1800"))
POLL_SECONDS = float(os.environ.get("SMOKE_POLL_SECONDS", "2"))
POPULATION_SIZE = int(os.environ.get("SMOKE_POPULATION_SIZE", "4"))
N_PARTITIONS = int(os.environ.get("SMOKE_N_PARTITIONS", "1"))
MAX_EVALUATIONS = int(os.environ.get("SMOKE_MAX_EVALUATIONS", "8"))
N_WORKERS = int(os.environ.get("SMOKE_N_WORKERS", "1"))
SEED = int(os.environ.get("SMOKE_SEED", "20260916"))
EXCLUDED_MINERS = sorted({"ilp", "hybrid_ilp"} | {
    item.strip() for item in os.environ.get("SMOKE_EXCLUDED_MINERS", "").split(",") if item.strip()
})
CONFORMANCE_MODE = os.environ.get("SMOKE_CONFORMANCE_MODE", "replay-token")
METRICS = ["fitness", "precision", "generalisation", "simplicity"]


class ValidationError(RuntimeError):
    pass


def request(path: str, *, base_url: str = API_URL, method: str = "GET", payload: Any = None) -> tuple[Any, dict[str, str]]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"{method} {base_url}{path} failed: {error.reason}") from error
    content_type = response_headers.get("content-type", "")
    if "json" in content_type:
        return json.loads(body.decode("utf-8")), response_headers
    return body, response_headers


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_marking(marking: Any, place_ids: set[str], label: str) -> None:
    require(isinstance(marking, list), f"{label} must be a list")
    seen: set[str] = set()
    for entry in marking:
        require(isinstance(entry, dict), f"{label} contains a non-object entry")
        place_id = entry.get("place_id")
        tokens = entry.get("tokens")
        require(isinstance(place_id, str) and place_id in place_ids, f"{label} references unknown place {place_id!r}")
        require(place_id not in seen, f"{label} contains duplicate place {place_id!r}")
        require(isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0,
                f"{label} has invalid token multiplicity {tokens!r}")
        seen.add(place_id)


def validate_solution(solution: dict[str, Any], label: str) -> None:
    schema_version = solution.get("model_schema_version")
    require(schema_version in (2, 3), f"{label}: unsupported model_schema_version")
    for field in (
        "places", "transitions", "initial_marking", "final_marking", "final_markings",
        "visible_transition_count", "is_feasible", "constraint_violations", "is_pareto",
    ):
        require(field in solution, f"{label}: missing field {field}")

    places = solution["places"]
    transitions = solution["transitions"]
    require(isinstance(places, list), f"{label}: places must be a list")
    require(isinstance(transitions, list), f"{label}: transitions must be a list")
    place_ids = {
        place.get("id") for place in places
        if isinstance(place, dict) and isinstance(place.get("id"), str)
    }
    require(len(place_ids) == len(places), f"{label}: places contain missing or duplicate IDs")

    validate_marking(solution["initial_marking"], place_ids, f"{label}.initial_marking")
    validate_marking(solution["final_marking"], place_ids, f"{label}.final_marking")
    final_markings = solution["final_markings"]
    require(isinstance(final_markings, list) and final_markings,
            f"{label}: final_markings must contain the evaluation final marking")
    for index, marking in enumerate(final_markings):
        validate_marking(marking, place_ids, f"{label}.final_markings[{index}]")
    require(solution["final_marking"] == final_markings[0],
            f"{label}: representative final_marking differs from final_markings[0]")

    visible_count = 0
    transition_ids: set[str] = set()
    for transition in transitions:
        require(isinstance(transition, dict), f"{label}: transition is not an object")
        require("invisible" in transition and isinstance(transition["invisible"], bool),
                f"{label}: transition lacks boolean invisible")
        transition_id = transition.get("id")
        require(isinstance(transition_id, str) and transition_id not in transition_ids,
                f"{label}: transition has missing or duplicate ID")
        transition_ids.add(transition_id)
        visible_count += int(not transition["invisible"])

    reported_count = solution["visible_transition_count"]
    require(isinstance(reported_count, int) and not isinstance(reported_count, bool),
            f"{label}: visible_transition_count is not an integer")
    require(reported_count == visible_count,
            f"{label}: visible_transition_count={reported_count}, actual={visible_count}")
    feasible = solution["is_feasible"]
    require(isinstance(feasible, bool), f"{label}: is_feasible is not boolean")
    violations = solution["constraint_violations"]
    if schema_version == 2:
        require(feasible == (reported_count > 0), f"{label}: v2 feasibility contradicts visible count")
        require(violations == ([] if feasible else ["NO_VISIBLE_TRANSITIONS"]),
                f"{label}: v2 constraint_violations contradict feasibility")
    else:
        require(isinstance(violations, list) and len(violations) == len(set(violations)),
                f"{label}: v3 constraint_violations are invalid")
        require(feasible == (len(violations) == 0), f"{label}: v3 feasibility contradicts violations")
        require((reported_count == 0) == ("NO_VISIBLE_TRANSITIONS" in violations),
                f"{label}: v3 visibility contradicts violations")
        require((len(final_markings) != 1) == ("MULTIPLE_FINAL_MARKINGS" in violations),
                f"{label}: v3 final marking count contradicts violations")
    require(isinstance(solution["is_pareto"], bool), f"{label}: is_pareto is not boolean")
    require(feasible or not solution["is_pareto"], f"{label}: infeasible solution is public Pareto")


def dominates(left: list[float], right: list[float]) -> bool:
    return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))


def validate_pareto(solutions: list[dict[str, Any]]) -> set[int]:
    feasible_indexes = [
        index for index, solution in enumerate(solutions)
        if solution.get("model_schema_version") in (2, 3) and solution.get("is_feasible") is True
    ]
    for index in feasible_indexes:
        solution = solutions[index]
        objectives = solution.get("objectives")
        require(isinstance(objectives, list) and objectives, f"solution[{index}]: objectives are missing")
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                    for value in objectives), f"solution[{index}]: objectives are invalid")
    expected = {
        index for index in feasible_indexes
        if not any(
            other != index and dominates(solutions[other]["objectives"], solutions[index]["objectives"])
            for other in feasible_indexes
        )
    }
    actual = {index for index, solution in enumerate(solutions) if solution["is_pareto"]}
    require(actual == expected, f"Pareto mismatch: API={sorted(actual)}, recomputed={sorted(expected)}")
    return expected


def json_cell(row: dict[str, str], field: str) -> Any:
    try:
        return json.loads(row[field])
    except (KeyError, json.JSONDecodeError) as error:
        raise ValidationError(f"export field {field!r} is missing or invalid JSON") from error


def validate_export(payload: bytes, solutions: list[dict[str, Any]]) -> tuple[list[str], int]:
    solution_count = len(solutions)
    by_id = {str(solution["solution_id"]): solution for solution in solutions}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        require("experiment.csv" in names, "export is missing experiment.csv")
        require("solutions.csv" in names, "export is missing solutions.csv")
        require("snapshot_solutions.csv" in names, "export is missing snapshot_solutions.csv")
        rows = list(csv.DictReader(io.TextIOWrapper(archive.open("solutions.csv"), encoding="utf-8")))
        require(len(rows) == solution_count,
                f"export has {len(rows)} solution rows; API returned {solution_count}")
        semantic_fields = {
            "model_schema_version", "places", "transitions", "visible_transition_count",
            "is_feasible", "constraint_violations", "is_pareto", "initial_marking",
            "final_marking", "final_markings",
        }
        require(not rows or semantic_fields.issubset(rows[0]), "export lacks model semantic columns")
        model_rows = 0
        for index, row in enumerate(rows):
            if not row["model_schema_version"]:
                require(row["is_pareto"].lower() != "true",
                        f"export.solution[{index}]: failed/legacy evaluation is Pareto")
                continue
            exported = {
                "model_schema_version": int(row["model_schema_version"]),
                "places": json_cell(row, "places"),
                "transitions": json_cell(row, "transitions"),
                "visible_transition_count": int(row["visible_transition_count"]),
                "is_feasible": row["is_feasible"].lower() == "true",
                "constraint_violations": json_cell(row, "constraint_violations"),
                "is_pareto": row["is_pareto"].lower() == "true",
                "initial_marking": json_cell(row, "initial_marking"),
                "final_marking": json_cell(row, "final_marking"),
                "final_markings": json_cell(row, "final_markings"),
            }
            validate_solution(exported, f"export.solution[{index}]")
            require(row["solution_id"] in by_id, "export contains an unknown solution ID")
            original = by_id[row["solution_id"]]
            for field in semantic_fields:
                require(exported[field] == original[field],
                        f"export.solution[{index}]: {field} differs from the persisted API value")
            model_rows += 1
    return names, model_rows


def main() -> int:
    started = time.monotonic()
    optimization_health, _ = request("/health")
    mining_health, _ = request("/health", base_url=MINING_URL)
    require(optimization_health.get("status") == "ok", "optimization service is not healthy")
    require(mining_health.get("status") == "ok", "mining service is not healthy")

    logs, _ = request("/logs")
    require(XES_LOG in logs.get("logs", []), f"XES log is not exposed by /logs: {XES_LOG}")

    execution_name = f"smoke_v3_{int(time.time())}"
    experiment_request = {
        "execution_name": execution_name,
        "log_path": XES_LOG,
        "metrics": METRICS,
        "conformance_mode": CONFORMANCE_MODE,
        "max_evaluations": MAX_EVALUATIONS,
        "population_size": POPULATION_SIZE,
        "n_partitions": N_PARTITIONS,
        "n_workers": N_WORKERS,
        "seed": SEED,
        "excluded_miners": EXCLUDED_MINERS,
    }
    print("request=" + json.dumps(experiment_request, sort_keys=True), flush=True)
    job, _ = request("/optimizations", method="POST", payload=experiment_request)
    job_id = job["job_id"]
    print(f"job_id={job_id}", flush=True)

    deadline = time.monotonic() + TIMEOUT_SECONDS
    previous = None
    while True:
        job, _ = request(f"/optimizations/{urllib.parse.quote(job_id)}")
        state = (job.get("status"), (job.get("progress") or {}).get("evaluations_done"))
        if state != previous:
            print(f"status={state[0]} evaluations={state[1]}/{MAX_EVALUATIONS}", flush=True)
            previous = state
        if job.get("status") in {"completed", "failed", "cancelled"}:
            break
        if time.monotonic() >= deadline:
            request(f"/optimizations/{urllib.parse.quote(job_id)}/cancel", method="POST")
            raise ValidationError(f"job {job_id} timed out and cancellation was requested")
        time.sleep(POLL_SECONDS)
    require(job.get("status") == "completed", f"job ended as {job.get('status')}: {job.get('error')}")

    all_payload, _ = request(f"/experiments/{urllib.parse.quote(job_id)}/solutions?scope=all")
    pareto_payload, _ = request(f"/experiments/{urllib.parse.quote(job_id)}/solutions?scope=pareto")
    solutions = all_payload.get("solutions", [])
    require(isinstance(solutions, list) and solutions, "completed experiment returned no solutions")
    v3_solutions = []
    for index, solution in enumerate(solutions):
        schema_version = solution.get("model_schema_version")
        require(schema_version in (None, 3), f"solution[{index}]: unexpected schema version {schema_version!r}")
        if schema_version == 3:
            validate_solution(solution, f"solution[{index}]")
            metrics = solution.get("metrics") or {}
            if solution.get("metrics_status") == "skipped_infeasible":
                require(solution.get("is_feasible") is False and not metrics,
                        f"solution[{index}]: skipped metrics require an infeasible model and an empty payload")
            else:
                require(all(isinstance(metrics.get(metric), (int, float))
                            and not isinstance(metrics.get(metric), bool)
                            and math.isfinite(metrics[metric]) and 0 <= metrics[metric] <= 1 for metric in METRICS),
                        f"solution[{index}]: requested token-replay metrics are missing or invalid")
            miner = (solution.get("pipeline") or {}).get("miner") or {}
            require(miner.get("key") not in EXCLUDED_MINERS
                    and miner.get("variant") not in {"Alpha#", "Alpha$"},
                    f"solution[{index}]: excluded miner/variant was evaluated")
            v3_solutions.append(solution)
        else:
            require(solution.get("is_pareto") is False,
                    f"solution[{index}]: failed/non-v3 evaluation is Pareto")
            require(solution.get("is_feasible") is None,
                    f"solution[{index}]: failed/non-v3 evaluation has feasibility metadata")
    require(v3_solutions, "completed experiment persisted no schema-v3 solutions")
    expected_pareto = validate_pareto(solutions)
    require(pareto_payload.get("count") == len(expected_pareto),
            "scope=pareto count differs from locally recomputed front")
    require(all(item.get("is_feasible") is True and item.get("is_pareto") is True
                for item in pareto_payload.get("solutions", [])),
            "scope=pareto returned a non-feasible or non-Pareto solution")

    export_payload, headers = request(f"/experiments/{urllib.parse.quote(job_id)}/download")
    require(isinstance(export_payload, bytes), "download endpoint did not return a ZIP")
    export_names, exported_v3 = validate_export(export_payload, solutions)
    require(exported_v3 == len(v3_solutions), "export schema-v3 row count differs from the API")
    export_path = Path(os.environ.get("SMOKE_EXPORT_PATH", f"/tmp/minersweeper-smoke-{job_id}.zip"))
    export_path.write_bytes(export_payload)

    duration = time.monotonic() - started
    miners = sorted({
        str((solution.get("pipeline") or {}).get("miner", {}).get("variant") or "")
        for solution in solutions
    })
    summary = {
        "job_id": job_id,
        "execution_name": execution_name,
        "xes": XES_LOG,
        "duration_seconds": round(duration, 1),
        "requested_evaluations": MAX_EVALUATIONS,
        "solutions": len(solutions),
        "schema_v3_solutions": len(v3_solutions),
        "failed_or_legacy_solutions": len(solutions) - len(v3_solutions),
        "feasible_solutions": sum(solution.get("is_feasible") is True for solution in solutions),
        "pareto_solutions": len(expected_pareto),
        "snapshots": (job.get("result_summary") or {}).get("counts", {}).get("snapshots"),
        "excluded_reasons": sorted({
            reason for solution in solutions for reason in solution.get("constraint_violations", [])
        }),
        "observed_miner_variants": miners,
        "export_path": str(export_path),
        "export_entries": export_names,
        "content_disposition": headers.get("content-disposition"),
        "validation": {
            "schema_v3": "PASS",
            "markings": "PASS",
            "invisibility": "PASS",
            "visible_count": "PASS",
            "feasibility": "PASS",
            "pareto": "PASS",
            "export": "PASS",
            "metrics": "PASS",
            "api_export_equality": "PASS",
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValidationError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"SMOKE FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
