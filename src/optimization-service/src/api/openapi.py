from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request
from optimization_defaults import DEFAULT_MAX_EVALUATIONS, DEFAULT_N_PARTITIONS, DEFAULT_POPULATION_SIZE


bp = Blueprint("optimization_openapi", __name__)


def _schema_ref(name: str) -> Dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _components() -> Dict[str, Any]:
    return {
        "schemas": {
            "JobStatus": {
                "type": "string",
                "enum": ["queued", "running", "cancelling", "cancelled", "completed", "failed"],
                "example": "running",
            },
            "ErrorResponse": {
                "type": "object",
                "required": ["error", "message"],
                "properties": {
                    "error": {"type": "string", "example": "invalid_request"},
                    "message": {"type": "string", "example": "scope must be 'pareto' or 'all'"},
                },
            },
            "HealthResponse": {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string", "example": "ok"}},
            },
            "LogsResponse": {
                "type": "object",
                "required": ["logs"],
                "properties": {
                    "logs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["BPI_Challenge_2013_open_problems.xes"],
                    }
                },
            },
            "OptimizationRequest": {
                "type": "object",
                "required": ["log_path"],
                "properties": {
                    "execution_name": {"type": "string", "example": "run_1"},
                    "log_path": {"type": "string", "example": "BPI_Challenge_2013_open_problems.xes"},
                    "service_url": {"type": "string", "format": "uri", "example": "http://prom_service:7070"},
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["fitness", "precision", "simplicity", "generalisation"],
                    },
                    "conformance_mode": {
                        "type": "string",
                        "enum": ["alignment", "replay", "replay-token"],
                        "default": "replay-token", "example": "replay-token",
                    },
                    "excluded_miners": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["ilp"],
                    },
                    "max_evaluations": {
                        "type": "integer", "default": DEFAULT_MAX_EVALUATIONS, "example": DEFAULT_MAX_EVALUATIONS,
                    },
                    "population_size": {
                        "type": "integer", "default": DEFAULT_POPULATION_SIZE, "example": DEFAULT_POPULATION_SIZE,
                    },
                    "n_partitions": {
                        "type": "integer", "nullable": True, "default": DEFAULT_N_PARTITIONS, "example": DEFAULT_N_PARTITIONS,
                    },
                    "n_workers": {"type": "integer", "example": 2},
                    "seed": {"type": "integer", "minimum": 0, "maximum": 9007199254740991, "example": 123456789},
                },
            },
            "JobProgress": {
                "type": "object",
                "required": ["job_id", "status", "evaluations_done", "max_evaluations", "percentage"],
                "properties": {
                    "job_id": {"type": "string", "format": "uuid"},
                    "status": _schema_ref("JobStatus"),
                    "evaluations_done": {"type": "integer", "example": 7},
                    "max_evaluations": {"type": "integer", "example": 50},
                    "percentage": {"type": "number", "format": "float", "example": 14.0},
                },
            },
            "JobRequestInfo": {
                "type": "object",
                "properties": {
                    "execution_name": {"type": "string"},
                    "log_path": {"type": "string"},
                    "service_url": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "required_metrics": {"type": "array", "items": {"type": "string"}},
                    "conformance_mode": {"type": "string", "nullable": True},
                    "excluded_miners": {"type": "array", "items": {"type": "string"}},
                    "discover": {
                        "type": "object",
                        "properties": {
                            "max_evaluations": {"type": "integer"},
                            "population_size": {"type": "integer"},
                            "n_partitions": {"type": "integer", "nullable": True},
                            "n_workers": {"type": "integer"},
                            "seed": {"type": "integer", "nullable": True},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": True,
            },
            "JobResultSummary": {
                "type": "object",
                "properties": {
                    "execution_name": {"type": "string"},
                    "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "pareto_evaluation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
            "Job": {
                "type": "object",
                "required": ["job_id", "status", "created_at", "request", "progress"],
                "properties": {
                    "job_id": {"type": "string", "format": "uuid"},
                    "status": _schema_ref("JobStatus"),
                    "created_at": {"type": "string", "format": "date-time"},
                    "started_at": {"type": "string", "format": "date-time", "nullable": True},
                    "finished_at": {"type": "string", "format": "date-time", "nullable": True},
                    "error": {"type": "string", "nullable": True},
                    "request": _schema_ref("JobRequestInfo"),
                    "progress": _schema_ref("JobProgress"),
                    "result_summary": _schema_ref("JobResultSummary"),
                },
                "additionalProperties": True,
            },
            "JobsResponse": {
                "type": "object",
                "required": ["jobs"],
                "properties": {
                    "jobs": {"type": "array", "items": _schema_ref("Job")},
                },
            },
            "Solution": {
                "type": "object",
                "properties": {
                    "evaluation_id": {"type": "string", "nullable": True},
                    "experiment_id": {"type": "string", "nullable": True},
                    "fingerprint": {"type": "string", "nullable": True},
                    "pipeline": {"type": "object", "additionalProperties": True},
                    "pipeline_full": {"type": "object", "nullable": True, "additionalProperties": True},
                    "evaluation_status": {"type": "string", "nullable": True},
                    "metrics": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "example": {"fitness": 0.91, "precision": 0.55, "simplicity": 0.7},
                    },
                    "objective_metrics": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "example": {"fitness": -0.91, "precision": -0.55},
                    },
                    "runtime_ms": {"type": "integer", "nullable": True, "example": 321},
                    "objectives": {"type": "array", "items": {"type": "number"}, "example": [-0.91, -0.55]},
                    "variables": {"type": "array", "items": {}},
                    "is_pareto": {"type": "boolean", "example": True},
                    "visible_transition_count": {"type": "integer", "nullable": True},
                    "is_feasible": {"type": "boolean", "nullable": True},
                    "constraint_violations": {"type": "array", "items": {"type": "string"}},
                    "evaluation_error": {"type": "string", "nullable": True},
                    "places": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "transitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "invisible": {"type": "boolean"},
                                "is_invisible": {"type": "boolean"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "arcs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "model_schema_version": {"type": "integer", "nullable": True},
                    "initial_marking": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "final_marking": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "final_markings": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                        },
                    },
                },
                "additionalProperties": True,
            },
            "SolutionsResponse": {
                "type": "object",
                "required": ["count", "solutions"],
                "properties": {
                    "job_id": {"type": "string", "format": "uuid"},
                    "experiment_id": {"type": "string"},
                    "scope": {"type": "string", "example": "pareto"},
                    "count": {"type": "integer", "example": 1},
                    "solutions": {"type": "array", "items": _schema_ref("Solution")},
                },
                "additionalProperties": True,
            },
            "Experiment": {
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "experiment_name": {"type": "string"},
                    "start_at": {"type": "string", "format": "date-time"},
                    "end_at": {"type": "string", "format": "date-time"},
                    "max_evals": {"type": "integer"},
                    "pop_size": {"type": "integer", "nullable": True},
                    "workers": {"type": "integer"},
                    "seed": {"type": "integer", "nullable": True},
                    "log_path": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "miners": {"type": "array", "items": {"type": "string"}},
                    "preprocessing": {"type": "array", "items": {"type": "string"}},
                    "actual_evaluations": {"type": "integer", "nullable": True},
                    "conformance_mode": {"type": "string", "nullable": True},
                    "log_sha256": {"type": "string", "nullable": True},
                    "optimizer_source_sha256": {"type": "string", "nullable": True},
                    "prom_revision": {"type": "string", "nullable": True},
                    "quality_policy_version": {"type": "string", "nullable": True},
                    "optimizer_config": {"type": "object", "nullable": True, "additionalProperties": True},
                    "population_snapshots": {"type": "array", "items": _schema_ref("PopulationSnapshot")},
                },
                "additionalProperties": True,
            },
            "PopulationSnapshot": {
                "type": "object",
                "properties": {
                    "snapshot_id": {"type": "integer"},
                    "experiment_id": {"type": "string"},
                    "snapshot_index": {"type": "integer"},
                    "evaluations_done": {"type": "integer"},
                    "attempts_since_previous": {"type": "integer", "nullable": True},
                    "cache_hits_since_previous": {"type": "integer", "nullable": True},
                    "errors_since_previous": {"type": "integer", "nullable": True},
                    "unique_pipelines_since_previous": {"type": "integer", "nullable": True},
                },
            },
            "ExperimentsResponse": {
                "type": "object",
                "required": ["experiments"],
                "properties": {
                    "experiments": {"type": "array", "items": _schema_ref("Experiment")},
                },
            },
            "ModelSelectionRequest": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["pareto", "all"], "default": "pareto"},
                    "weights": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "example": {"fitness": 80, "precision": 20},
                    },
                },
                "additionalProperties": False,
            },
            "ModelSelectionResponse": {
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "scope": {"type": "string"},
                    "selection_method": {"type": "string", "example": "asf"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "slider_weights": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "example": {"fitness": 80, "precision": 20},
                    },
                    "normalized_weights": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "example": {"fitness": 0.8, "precision": 0.2},
                    },
                    "candidate_count": {"type": "integer", "example": 2},
                    "selected_solution_id": {"type": "integer", "example": 7},
                    "selected_solution": _schema_ref("Solution"),
                    "scalarized_objective": {"type": "number", "example": 0.25},
                    "approx_ideal": {"type": "array", "items": {"type": "number"}, "example": [-0.91, -0.55]},
                    "approx_nadir": {"type": "array", "items": {"type": "number"}, "example": [-0.8, -0.3]},
                },
                "additionalProperties": True,
            },
            "PetriRenderRequest": {
                "type": "object",
                "properties": {
                    "places": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "transitions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "arcs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "initial_marking": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "final_marking": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "final_markings": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                        },
                    },
                    "format": {"type": "string", "enum": ["svg", "png"], "default": "svg"},
                },
                "additionalProperties": True,
            },
        }
    }


def _json_content(schema_name: str, *, example: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"schema": _schema_ref(schema_name)}
    if example is not None:
        payload["example"] = example
    return {"application/json": payload}


def _error_responses(*status_codes: str) -> Dict[str, Any]:
    messages = {
        "400": "Invalid request",
        "404": "Resource not found",
        "409": "Invalid state",
        "429": "Another exploration analysis is running",
        "500": "Internal server error",
    }
    return {
        code: {
            "description": messages[code],
            "content": _json_content("ErrorResponse"),
        }
        for code in status_codes
    }


def _paths() -> Dict[str, Any]:
    return {
        "/health": {
            "get": {
                "tags": ["system"],
                "summary": "Service health check",
                "operationId": "health",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": _json_content("HealthResponse"),
                    }
                },
            }
        },
        "/logs": {
            "get": {
                "tags": ["system"],
                "summary": "List available XES logs",
                "operationId": "listLogs",
                "responses": {
                    "200": {
                        "description": "Available logs under LOGS_ROOT",
                        "content": _json_content("LogsResponse"),
                    }
                },
            }
        },
        "/optimizations": {
            "get": {
                "tags": ["jobs"],
                "summary": "List optimization jobs",
                "operationId": "listOptimizations",
                "responses": {
                    "200": {
                        "description": "Jobs currently known by the service",
                        "content": _json_content("JobsResponse"),
                    }
                },
            },
            "post": {
                "tags": ["jobs"],
                "summary": "Create an optimization job",
                "operationId": "createOptimization",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("OptimizationRequest"),
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Job accepted and queued",
                        "content": _json_content("Job"),
                    },
                    **_error_responses("400"),
                },
            },
        },
        "/optimizations/{job_id}": {
            "get": {
                "tags": ["jobs"],
                "summary": "Get one optimization job",
                "operationId": "getOptimization",
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Job state",
                        "content": _json_content("Job"),
                    },
                    **_error_responses("404"),
                },
            }
        },
        "/optimizations/{job_id}/cancel": {
            "post": {
                "tags": ["jobs"],
                "summary": "Request cancellation of an optimization job",
                "operationId": "cancelOptimization",
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "202": {
                        "description": "Cancellation accepted",
                        "content": _json_content("Job"),
                    },
                    **_error_responses("404", "409"),
                },
            }
        },
        "/optimizations/{job_id}/progress": {
            "get": {
                "tags": ["jobs"],
                "summary": "Get job progress",
                "operationId": "getOptimizationProgress",
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Progress snapshot",
                        "content": _json_content("JobProgress"),
                    },
                    **_error_responses("404"),
                },
            }
        },
        "/optimizations/{job_id}/events": {
            "get": {
                "tags": ["jobs"],
                "summary": "Stream job events as server-sent events",
                "operationId": "streamOptimizationEvents",
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "SSE stream with status_changed, progress and result_ready events",
                        "content": {
                            "text/event-stream": {
                                "schema": {
                                    "type": "string",
                                    "example": "event: progress\\ndata: {\"job_id\":\"...\",\"percentage\":14.0}\\n\\n",
                                }
                            }
                        },
                    },
                    **_error_responses("404"),
                },
            }
        },
        "/optimizations/{job_id}/solutions": {
            "get": {
                "tags": ["jobs"],
                "summary": "Get job solutions",
                "operationId": "getOptimizationSolutions",
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    },
                    {
                        "name": "scope",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["pareto", "all"], "default": "pareto"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Solutions for a completed job",
                        "content": _json_content("SolutionsResponse"),
                    },
                    **_error_responses("400", "404", "409"),
                },
            }
        },
        "/experiments": {
            "get": {
                "tags": ["experiments"],
                "summary": "List persisted experiments",
                "operationId": "listExperiments",
                "responses": {
                    "200": {
                        "description": "Persisted experiments",
                        "content": _json_content("ExperimentsResponse"),
                    }
                },
            }
        },
        "/experiments/{experiment_id}": {
            "get": {
                "tags": ["experiments"],
                "summary": "Get one experiment",
                "operationId": "getExperiment",
                "parameters": [
                    {
                        "name": "experiment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Experiment metadata",
                        "content": _json_content("Experiment"),
                    },
                    **_error_responses("404"),
                },
            },
            "delete": {
                "tags": ["experiments"],
                "summary": "Delete one persisted experiment",
                "operationId": "deleteExperiment",
                "parameters": [
                    {
                        "name": "experiment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Experiment deleted",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["experiment_id", "deleted"],
                                    "properties": {
                                        "experiment_id": {"type": "string"},
                                        "deleted": {"type": "boolean"},
                                    },
                                }
                            }
                        },
                    },
                    **_error_responses("404"),
                },
            },
        },
        "/experiments/{experiment_id}/solutions": {
            "get": {
                "tags": ["experiments"],
                "summary": "Get persisted experiment solutions",
                "operationId": "getExperimentSolutions",
                "parameters": [
                    {
                        "name": "experiment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "scope",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["pareto", "all"], "default": "all"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Persisted solutions",
                        "content": _json_content("SolutionsResponse"),
                    },
                    **_error_responses("400", "404"),
                },
            }
        },
        "/experiments/{experiment_id}/select-model": {
            "post": {
                "tags": ["experiments"],
                "summary": "Select one model from an experiment result set",
                "operationId": "selectExperimentModel",
                "parameters": [
                    {
                        "name": "experiment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": False,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("ModelSelectionRequest"),
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Model selection result",
                        "content": _json_content("ModelSelectionResponse"),
                    },
                    **_error_responses("400", "404", "409"),
                },
            }
        },
        "/experiments/{experiment_id}/download": {
            "get": {
                "tags": ["experiments"],
                "summary": "Download experiment export as ZIP",
                "operationId": "downloadExperiment",
                "parameters": [
                    {
                        "name": "experiment_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "ZIP archive with experiment data",
                        "content": {
                            "application/zip": {
                                "schema": {"type": "string", "format": "binary"}
                            }
                        },
                    },
                    **_error_responses("404"),
                },
            }
        },
        "/petri/render": {
            "post": {
                "tags": ["petri"],
                "summary": "Render a Petri net as SVG or PNG",
                "operationId": "renderPetri",
                "parameters": [
                    {
                        "name": "format",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["svg", "png"], "default": "svg"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("PetriRenderRequest"),
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Rendered Petri net image",
                        "content": {
                            "image/svg+xml": {"schema": {"type": "string", "format": "binary"}},
                            "image/png": {"schema": {"type": "string", "format": "binary"}},
                        },
                    },
                    **_error_responses("400", "500"),
                },
            }
        },
    }


def _exploration_paths() -> Dict[str, Any]:
    operations = [
        ("/experiments/{experiment_id}/explorations", "post", "createExploration", "Analyze every individual in the final population"),
        ("/explorations/{exploration_id}", "get", "getExploration", "Analysis status, source models and statistics"),
        ("/explorations/{exploration_id}/cancel", "post", "cancelExploration", "Request cooperative cancellation"),
        ("/explorations/{exploration_id}/views/{kind}", "get", "getExplorationView", "Structural overlay, regions or common/variable template"),
        ("/explorations/{exploration_id}/models/{model_id}", "get", "getExplorationModel", "Original Petri graph, markings, metrics and provenance"),
        ("/explorations/{exploration_id}/models/{model_id}/pnml", "get", "downloadExplorationPnml", "Download the unmodified original PNML"),
    ]
    paths = {}
    for path, method, operation, summary in operations:
        binary = path.endswith("/pnml")
        parameters = [{"name": name, "in": "path", "required": True,
                       "schema": {"type": "string", **({"enum": ["merging", "variation", "template"]} if name == "kind" else {})}}
                      for name in ("experiment_id", "exploration_id", "kind", "model_id") if "{" + name + "}" in path]
        paths[path] = {method: {"tags": ["explorations"], "operationId": operation, "summary": summary,
                              "parameters": parameters,
                              "responses": {"200": {"description": summary, "content": {
                                  "application/xml" if binary else "application/json": {"schema": {"type": "string", "format": "binary"} if binary else {"type": "object"}}}},
                                  **({"202": {"description": "Analysis running"}} if operation == "createExploration" else {}),
                                  **_error_responses("400", "404", "409", "429")}}}
        if operation == 'createExploration':
            paths[path][method]['requestBody'] = {"required": False, "content": {"application/json": {"schema": {
                "type": "object", "properties": {"representation": {"type": "string", "enum": ["petri", "bpmn"], "default": "petri"}}}}}}
    paths["/explorations/import"] = {"post": {
        "tags": ["explorations"], "operationId": "importExplorationPopulation",
        "summary": "Import the final population from a common export with original PNML and metadata",
        "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["archive"], "properties": {
                "archive": {"type": "string", "format": "binary"},
                "originals": {"type": "array", "items": {"type": "string", "format": "binary"}}}}}}},
        "responses": {"201": {"description": "Imported experiment ID", "content": {"application/json": {"schema": {"type": "object"}}}}, **_error_responses("400")},
    }}
    return paths


def build_openapi_spec(server_url: str) -> Dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Minersweeper Optimization API",
            "version": "0.1.0",
            "description": (
                "HTTP API for optimization jobs, experiment inspection, model selection and Petri net rendering."
            ),
        },
        "servers": [{"url": server_url.rstrip("/")}],
        "tags": [
            {"name": "system", "description": "Operational endpoints"},
            {"name": "jobs", "description": "Optimization job lifecycle and runtime data"},
            {"name": "experiments", "description": "Persisted experiment inspection and exports"},
            {"name": "petri", "description": "Petri net rendering utilities"},
            {"name": "explorations", "description": "Experimental structural exploration of the complete final population"},
        ],
        "paths": {**_paths(), **_exploration_paths()},
        "components": _components(),
    }


def _swagger_ui_html(openapi_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Minersweeper API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    <style>
      body {{
        margin: 0;
        background: #f5f7fb;
      }}
      .topbar {{
        display: none;
      }}
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      window.ui = SwaggerUIBundle({{
        url: {openapi_url!r},
        dom_id: '#swagger-ui',
        deepLinking: true,
        displayRequestDuration: true,
        persistAuthorization: false
      }});
    </script>
  </body>
</html>
"""


@bp.get("/openapi.json")
def openapi_spec() -> Any:
    return jsonify(build_openapi_spec(request.url_root.rstrip("/")))


@bp.get("/docs")
def swagger_ui() -> Any:
    openapi_url = f"{request.script_root.rstrip('/')}/openapi.json" if request.script_root else "/openapi.json"
    return Response(_swagger_ui_html(openapi_url), mimetype="text/html")
