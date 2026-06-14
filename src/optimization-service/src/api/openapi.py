from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request


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
            "Constraint": {
                "type": "object",
                "required": ["metric", "operator", "value"],
                "properties": {
                    "metric": {"type": "string", "example": "places"},
                    "operator": {"type": "string", "example": "<="},
                    "value": {"type": "number", "example": 12},
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
                    "constraints": {
                        "type": "array",
                        "items": _schema_ref("Constraint"),
                    },
                    "conformance_mode": {
                        "type": "string",
                        "enum": ["alignment", "replay", "replay_token"],
                        "example": "alignment",
                    },
                    "excluded_miners": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["ilp"],
                    },
                    "max_evaluations": {"type": "integer", "example": 1000},
                    "population_size": {"type": "integer", "example": 100},
                    "n_partitions": {"type": "integer", "nullable": True, "example": 4},
                    "n_workers": {"type": "integer", "example": 2},
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
                    "constraints": {"type": "array", "items": _schema_ref("Constraint")},
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
                    "constraints": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "constraint_violations": {"type": "array", "items": {"type": "number"}, "example": [0.0, -1.0]},
                    "is_feasible": {"type": "boolean", "example": True},
                    "runtime_ms": {"type": "integer", "nullable": True, "example": 321},
                    "objectives": {"type": "array", "items": {"type": "number"}, "example": [-0.91, -0.55]},
                    "constraint_values": {"type": "array", "items": {"type": "number"}},
                    "variables": {"type": "array", "items": {}},
                    "is_pareto": {"type": "boolean", "example": True},
                    "evaluation_error": {"type": "string", "nullable": True},
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
                    "log_path": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "constraints": {"type": "array", "items": _schema_ref("Constraint")},
                    "miners": {"type": "array", "items": {"type": "string"}},
                    "preprocessing": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
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
                    "feasible_only": {"type": "boolean", "default": False},
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
                    "feasible_only": {"type": "boolean", "example": False},
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
            }
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
        ],
        "paths": _paths(),
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
