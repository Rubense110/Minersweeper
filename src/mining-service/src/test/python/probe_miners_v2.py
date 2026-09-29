#!/usr/bin/env python3
"""Probe the 14 active miner variants through the real token-replay API."""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


BASE_URL = os.environ.get("MINERSWEEPER_MINING_URL", "http://localhost:7070").rstrip("/")
LOG_PATH = os.environ.get("PROBE_XES", "/data/logs/BPI_Challenge_2013_open_problems.xes")
METRICS = ["fitness", "precision", "generalisation", "simplicity"]

PREPROCESSING = {
    "key": "matrix_filter",
    "method": "Matrix Filtering",
    "variant": "Conditional Probabilities (MF)",
    "parameters": {"probability_of_removal_mf": 0.15, "subsequence_length_mf": 2},
}

# Exact configurations from src/mining-service/src/test/java/TestFixtures.java.
MINERS = [
    {
        "key": "alpha", "family": "alpha", "variant": "Alpha",
        "parameters": {"alpha_version": "CLASSIC"},
    },
    {
        "key": "heuristics", "family": "heuristics", "variant": "Heuristics Miner",
        "parameters": {
            "relative_to_best_threshold": 0.05,
            "positive_observation_threshold": 1,
            "dependency_threshold": 0.90,
            "l1l_threshold": 0.90,
            "l2l_threshold": 0.90,
            "long_distance_threshold": 0.90,
            "dependency_divisor": 1,
            "and_threshold": 0.10,
            "extra_info": False,
            "use_all_connected_heuristics": True,
            "use_long_distance_dependency": False,
            "check_best_against_l2l": True,
        },
    },
    {
        "key": "inductive", "family": "inductive", "variant": "Inductive Miner - infrequent (IMf)",
        "parameters": {"noise_threshold": 0.2, "is_debug": False, "use_multithreading": False},
    },
    {
        "key": "split", "family": "split", "variant": "Split Miner",
        "parameters": {"epsilon": 0.5, "eta": 0.5},
    },
]

# ILP/Hybrid ILP are excluded by the frontend; Alpha#/Alpha$ were retired.
MINERS.extend({"key": "alpha", "family": "alpha", "variant": variant,
               "parameters": {"alpha_version": version}}
              for variant, version in [("Alpha+", "PLUS"), ("Alpha++", "PLUS_PLUS"), ("AlphaR", "ROBUST")])
MINERS.append({**MINERS[1], "variant": "Flexible Heuristics Miner"})
MINERS.extend({"key": "inductive", "family": "inductive", "variant": variant,
               "parameters": {"noise_threshold": 0.2, "is_debug": False, "use_multithreading": False}}
              for variant in ["Inductive Miner (IM)", "Inductive Miner - life cycle (IMlc)",
                              "Inductive Miner - infrequent & life cycle (IMflc)",
                              "Inductive Miner - partial traces (IMpt)",
                              "Inductive Miner - infrequent & partial traces (IMfpt)",
                              "Inductive Miner - infrequent & partial traces Ali (IMfpta)"])


def http_json(path: str, *, payload: Any = None) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return error.code, parsed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_marking(marking: Any, place_ids: set[str], field: str) -> None:
    require(isinstance(marking, list), f"{field} is not a list")
    for entry in marking:
        require(isinstance(entry, dict), f"{field} contains a non-object")
        require(entry.get("place_id") in place_ids, f"{field} contains an unknown place")
        tokens = entry.get("tokens")
        require(isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0,
                f"{field} contains invalid token multiplicity")


def validate_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    require(artifact.get("model_schema_version") == 2, "model_schema_version is not 2")
    places = artifact.get("places")
    if not isinstance(places, list):
        # The Java artifact API exposes PNML plus semantic fields, not parsed places.
        import xml.etree.ElementTree as element_tree
        root = element_tree.fromstring(artifact.get("pnml") or "")
        place_ids = {
            node.attrib.get("id") for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "place"
        }
    else:
        place_ids = {place.get("id") for place in places if isinstance(place, dict)}
    require(all(isinstance(place_id, str) and place_id for place_id in place_ids), "PNML has invalid place IDs")

    initial = artifact.get("initial_marking")
    final = artifact.get("final_marking")
    finals = artifact.get("final_markings")
    validate_marking(initial, place_ids, "initial_marking")
    validate_marking(final, place_ids, "final_marking")
    require(isinstance(finals, list) and finals, "final_markings is missing or empty")
    for index, marking in enumerate(finals):
        validate_marking(marking, place_ids, f"final_markings[{index}]")
    require(final == finals[0], "final_marking differs from the evaluation marking")

    transitions = artifact.get("transitions")
    require(isinstance(transitions, list), "transitions is not a list")
    require(all(isinstance(item, dict) and isinstance(item.get("invisible"), bool) for item in transitions),
            "a transition lacks boolean invisible")
    actual_visible = sum(not item["invisible"] for item in transitions)
    require(artifact.get("visible_transition_count") == actual_visible, "visible transition count mismatch")
    feasible = artifact.get("is_feasible")
    require(isinstance(feasible, bool) and feasible == (actual_visible > 0), "feasibility mismatch")
    expected = [] if feasible else ["NO_VISIBLE_TRANSITIONS"]
    require(artifact.get("constraint_violations") == expected, "constraint violations mismatch")
    return {
        "places": len(place_ids),
        "transitions": len(transitions),
        "initial_marking": initial,
        "final_marking": final,
        "final_markings": finals,
        "visible_transition_count": actual_visible,
        "is_feasible": feasible,
        "constraint_violations": expected,
    }


def main() -> int:
    health_status, health = http_json("/health")
    require(health_status == 200 and health.get("status") == "ok", "mining service is not healthy")
    run_id = f"probe_v2_{int(time.time())}"
    results: list[dict[str, Any]] = []
    selected_variants = {variant.strip() for variant in os.environ.get("PROBE_VARIANTS", "").split(",") if variant.strip()}
    selected_miners = [miner for miner in MINERS if not selected_variants or miner["variant"] in selected_variants]
    require(selected_miners, f"No active variant matched PROBE_VARIANTS={selected_variants}")

    for index, miner in enumerate(selected_miners):
        experiment_id = f"{run_id}_{index}_{miner['key']}"
        print(f"START {index + 1}/{len(selected_miners)} {miner['variant']} log={LOG_PATH}", flush=True)
        request_payload = {
            "experiment_id": experiment_id,
            "request_id": uuid.uuid4().hex,
            "log_path": LOG_PATH,
            "pipeline": {"preprocessing": PREPROCESSING, "miner": miner},
            "metrics": METRICS,
            "conformance_mode": "replay-token",
        }
        started = time.monotonic()
        status, response = http_json("/pipeline", payload=request_payload)
        row: dict[str, Any] = {
            "miner": miner["key"],
            "pipeline": miner,
            "http_status": status,
            "duration_seconds": round(time.monotonic() - started, 3),
            "discovery": "PASS" if status == 200 else "FAIL",
            "response": response,
            "artifact_v2": False,
        }
        if status == 200:
            metrics = response.get("metrics") or {}
            row["metrics_valid"] = all(
                isinstance(metrics.get(metric), (int, float))
                and not isinstance(metrics.get(metric), bool)
                and math.isfinite(metrics[metric]) and 0 <= metrics[metric] <= 1
                for metric in METRICS
            )
            evaluation_id = response.get("evaluation_id")
            artifact_status, artifact_response = http_json(
                "/artifacts/bulk",
                payload={
                    "experiment_id": experiment_id,
                    "evaluation_ids": [evaluation_id],
                    "include_pnml": True,
                },
            )
            row["artifact_http_status"] = artifact_status
            artifacts = artifact_response.get("artifacts", []) if isinstance(artifact_response, dict) else []
            if artifact_status == 200 and len(artifacts) == 1:
                try:
                    row["semantics"] = validate_artifact(artifacts[0])
                    row["artifact_v2"] = True
                except (ValueError, TypeError) as error:
                    row["artifact_validation_error"] = str(error)
            else:
                row["artifact_response"] = artifact_response
        results.append(row)
        print(json.dumps(row, ensure_ascii=True, sort_keys=True), flush=True)
        output_path = os.environ.get("PROBE_REPORT")
        if output_path:
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump({"run_id": run_id, "log_path": LOG_PATH, "results": results,
                           "complete": len(results) == len(selected_miners)},
                          handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.write("\n")

    return 0 if all(row["artifact_v2"] and row.get("metrics_valid") for row in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, urllib.error.URLError) as error:
        print(f"PROBE FAILED: {error}", file=sys.stderr)
        raise SystemExit(2)
