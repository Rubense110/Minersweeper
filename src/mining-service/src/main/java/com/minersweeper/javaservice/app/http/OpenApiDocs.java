package com.minersweeper.javaservice.app.http;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OpenApiDocs {
    private OpenApiDocs() {}

    public static Map<String, Object> buildSpec(String serverUrl) {
        Map<String, Object> spec = new LinkedHashMap<String, Object>();
        spec.put("openapi", "3.1.0");
        spec.put("info", info());
        spec.put("servers", Arrays.<Object>asList(server(serverUrl)));
        spec.put("tags", tags());
        spec.put("paths", paths());
        spec.put("components", components());
        return spec;
    }

    public static String swaggerUiHtml(String openapiUrl) {
        return "<!doctype html>\n"
            + "<html lang=\"en\">\n"
            + "  <head>\n"
            + "    <meta charset=\"utf-8\" />\n"
            + "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            + "    <title>Minersweeper Mining API Docs</title>\n"
            + "    <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />\n"
            + "    <style>\n"
            + "      body { margin: 0; background: #f5f7fb; }\n"
            + "      .topbar { display: none; }\n"
            + "    </style>\n"
            + "  </head>\n"
            + "  <body>\n"
            + "    <div id=\"swagger-ui\"></div>\n"
            + "    <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>\n"
            + "    <script>\n"
            + "      window.ui = SwaggerUIBundle({\n"
            + "        url: " + quoteJs(openapiUrl) + ",\n"
            + "        dom_id: '#swagger-ui',\n"
            + "        deepLinking: true,\n"
            + "        displayRequestDuration: true,\n"
            + "        persistAuthorization: false\n"
            + "      });\n"
            + "    </script>\n"
            + "  </body>\n"
            + "</html>\n";
    }

    private static Map<String, Object> info() {
        Map<String, Object> info = new LinkedHashMap<String, Object>();
        info.put("title", "Minersweeper Mining API");
        info.put("version", "0.1.0");
        info.put(
            "description",
            "HTTP API for pipeline evaluation, artifact retrieval, experiment cancellation and cleanup."
        );
        return info;
    }

    private static Map<String, Object> server(String serverUrl) {
        Map<String, Object> server = new LinkedHashMap<String, Object>();
        server.put("url", normalizeServerUrl(serverUrl));
        return server;
    }

    private static List<Object> tags() {
        List<Object> tags = new ArrayList<Object>();
        tags.add(tag("system", "Operational endpoints"));
        tags.add(tag("evaluation", "Pipeline evaluation and conformance metrics"));
        tags.add(tag("artifacts", "Stored PNML and evaluation artifacts"));
        tags.add(tag("experiments", "Experiment cancellation and cleanup"));
        return tags;
    }

    private static Map<String, Object> tag(String name, String description) {
        Map<String, Object> tag = new LinkedHashMap<String, Object>();
        tag.put("name", name);
        tag.put("description", description);
        return tag;
    }

    private static Map<String, Object> paths() {
        Map<String, Object> paths = new LinkedHashMap<String, Object>();
        paths.put("/health", healthPath());
        paths.put("/pipeline", pipelinePath());
        paths.put("/artifacts/bulk", artifactsBulkPath());
        paths.put("/experiments/{experimentId}/cancel", cancelPath());
        paths.put("/experiments/{experimentId}/cleanup", cleanupPath());
        return paths;
    }

    private static Map<String, Object> healthPath() {
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("tags", Arrays.<Object>asList("system"));
        operation.put("summary", "Service health");
        operation.put("operationId", "getHealth");
        Map<String, Object> responseMap = new LinkedHashMap<String, Object>();
        responseMap.put("200", response(200, "Service is healthy", inlineHealthSchema()));
        operation.put("responses", responseMap);
        return singleMethod("get", operation);
    }

    private static Map<String, Object> pipelinePath() {
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("tags", Arrays.<Object>asList("evaluation"));
        operation.put("summary", "Evaluate a mining pipeline");
        operation.put("operationId", "evaluatePipeline");
        operation.put(
            "description",
            "Discovers a Petri net from the requested preprocessing/miner pipeline and computes the requested metrics."
        );
        operation.put("requestBody", jsonRequestBody(schemaRef("PipelineRequest"), true));

        Map<String, Object> responseMap = new LinkedHashMap<String, Object>();
        responseMap.put("200", response(200, "Pipeline evaluation completed", schemaRef("PipelineResponse")));
        responseMap.put("400", errorResponse("Invalid JSON or invalid request payload"));
        responseMap.put("409", errorResponse("Experiment was cancelled while the evaluation was running"));
        responseMap.put("500", errorResponse("Unexpected evaluation failure"));
        operation.put("responses", responseMap);
        return singleMethod("post", operation);
    }

    private static Map<String, Object> artifactsBulkPath() {
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("tags", Arrays.<Object>asList("artifacts"));
        operation.put("summary", "Fetch stored artifacts for one or more evaluations");
        operation.put("operationId", "fetchArtifactsBulk");
        operation.put("requestBody", jsonRequestBody(schemaRef("ArtifactBulkRequest"), true));

        Map<String, Object> responseMap = new LinkedHashMap<String, Object>();
        responseMap.put("200", response(200, "Artifacts found", schemaRef("ArtifactBulkResponse")));
        responseMap.put("400", errorResponse("Invalid JSON or invalid request payload"));
        responseMap.put("404", errorResponse("One or more evaluation ids were not found"));
        responseMap.put("500", errorResponse("Artifact loading failed"));
        operation.put("responses", responseMap);
        return singleMethod("post", operation);
    }

    private static Map<String, Object> cancelPath() {
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("tags", Arrays.<Object>asList("experiments"));
        operation.put("summary", "Request cancellation of an experiment");
        operation.put("operationId", "cancelExperiment");
        operation.put("parameters", Arrays.<Object>asList(experimentIdParameter()));

        Map<String, Object> responseMap = new LinkedHashMap<String, Object>();
        responseMap.put("200", response(200, "Cancellation request accepted", schemaRef("ExperimentCancelResponse")));
        responseMap.put("400", errorResponse("Invalid experiment id"));
        responseMap.put("500", errorResponse("Cancellation request failed"));
        operation.put("responses", responseMap);
        return singleMethod("post", operation);
    }

    private static Map<String, Object> cleanupPath() {
        Map<String, Object> operation = new LinkedHashMap<String, Object>();
        operation.put("tags", Arrays.<Object>asList("experiments"));
        operation.put("summary", "Delete persisted artifacts for an experiment");
        operation.put("operationId", "cleanupExperiment");
        operation.put("parameters", Arrays.<Object>asList(experimentIdParameter()));

        Map<String, Object> responseMap = new LinkedHashMap<String, Object>();
        responseMap.put("200", response(200, "Cleanup completed", schemaRef("ExperimentCleanupResponse")));
        responseMap.put("400", errorResponse("Invalid experiment id"));
        responseMap.put("500", errorResponse("Cleanup failed"));
        operation.put("responses", responseMap);
        return singleMethod("post", operation);
    }

    private static Map<String, Object> experimentIdParameter() {
        Map<String, Object> parameter = new LinkedHashMap<String, Object>();
        parameter.put("name", "experimentId");
        parameter.put("in", "path");
        parameter.put("required", Boolean.TRUE);
        parameter.put("description", "Experiment identifier used to group evaluation artifacts.");
        parameter.put("schema", scalarSchema("string"));
        return parameter;
    }

    private static Map<String, Object> components() {
        Map<String, Object> components = new LinkedHashMap<String, Object>();
        Map<String, Object> schemas = new LinkedHashMap<String, Object>();
        schemas.put("HealthResponse", inlineHealthSchema());
        schemas.put("ErrorResponse", errorSchema());
        schemas.put("PipelineRequest", pipelineRequestSchema());
        schemas.put("PipelineResponse", pipelineResponseSchema());
        schemas.put("ArtifactBulkRequest", artifactBulkRequestSchema());
        schemas.put("ArtifactBulkResponse", artifactBulkResponseSchema());
        schemas.put("ArtifactEntry", artifactEntrySchema());
        schemas.put("ExperimentCancelResponse", experimentCancelResponseSchema());
        schemas.put("ExperimentCleanupResponse", experimentCleanupResponseSchema());
        schemas.put("PipelineConfig", pipelineConfigSchema());
        schemas.put("PreprocessingConfig", preprocessingConfigSchema());
        schemas.put("MinerConfig", minerConfigSchema());
        components.put("schemas", schemas);
        return components;
    }

    private static Map<String, Object> inlineHealthSchema() {
        Map<String, Object> schema = objectSchema("status");
        schema.put("properties", properties(property("status", stringConstSchema("ok"))));
        return schema;
    }

    private static Map<String, Object> errorSchema() {
        Map<String, Object> schema = objectSchema("error", "message");
        schema.put(
            "properties",
            properties(
                property("error", scalarSchema("string")),
                property("message", scalarSchema("string"))
            )
        );
        return schema;
    }

    private static Map<String, Object> pipelineRequestSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "log_path", "pipeline", "metrics");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("log_path", scalarSchema("string")),
                property("conformance_mode", stringEnumSchema("alignment", "replay", "replay-token")),
                property("pipeline", schemaRef("PipelineConfig")),
                property("metrics", arraySchema(scalarSchema("string"))),
                property("excluded_miners", arraySchema(scalarSchema("string")))
            )
        );
        return schema;
    }

    private static Map<String, Object> pipelineResponseSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "evaluation_id", "fingerprint", "metrics");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("evaluation_id", scalarSchema("string")),
                property("fingerprint", scalarSchema("string")),
                property("metrics", numberMapSchema())
            )
        );
        return schema;
    }

    private static Map<String, Object> artifactBulkRequestSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "evaluation_ids");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("evaluation_ids", arraySchema(scalarSchema("string"))),
                property("include_pnml", scalarSchema("boolean"))
            )
        );
        return schema;
    }

    private static Map<String, Object> artifactBulkResponseSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "artifacts");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("artifacts", arraySchema(schemaRef("ArtifactEntry")))
            )
        );
        return schema;
    }

    private static Map<String, Object> artifactEntrySchema() {
        Map<String, Object> schema = objectSchema(
            "experiment_id",
            "evaluation_id",
            "fingerprint",
            "log_path",
            "created_at_epoch_ms",
            "metrics",
            "pipeline"
        );
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("evaluation_id", scalarSchema("string")),
                property("fingerprint", scalarSchema("string")),
                property("log_path", scalarSchema("string")),
                property("created_at_epoch_ms", scalarSchema("integer", "int64")),
                property("metrics", numberMapSchema()),
                property("pipeline", schemaRef("PipelineConfig")),
                property("pnml", scalarSchema("string"))
            )
        );
        return schema;
    }

    private static Map<String, Object> experimentCancelResponseSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "cancel_requested");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("cancel_requested", scalarSchema("boolean"))
            )
        );
        return schema;
    }

    private static Map<String, Object> experimentCleanupResponseSchema() {
        Map<String, Object> schema = objectSchema("experiment_id", "deleted_paths", "deleted");
        schema.put(
            "properties",
            properties(
                property("experiment_id", scalarSchema("string")),
                property("deleted_paths", scalarSchema("integer", "int32")),
                property("deleted", scalarSchema("boolean"))
            )
        );
        return schema;
    }

    private static Map<String, Object> pipelineConfigSchema() {
        Map<String, Object> schema = objectSchema("miner");
        schema.put(
            "properties",
            properties(
                property("preprocessing", schemaRef("PreprocessingConfig")),
                property("preprocessings", arraySchema(schemaRef("PreprocessingConfig"))),
                property("miner", schemaRef("MinerConfig"))
            )
        );
        return schema;
    }

    private static Map<String, Object> preprocessingConfigSchema() {
        Map<String, Object> schema = objectSchema("key");
        schema.put(
            "properties",
            properties(
                property("key", scalarSchema("string")),
                property("method", scalarSchema("string")),
                property("variant", scalarSchema("string")),
                property("parameters", freeFormObjectSchema())
            )
        );
        return schema;
    }

    private static Map<String, Object> minerConfigSchema() {
        Map<String, Object> schema = objectSchema("key");
        schema.put(
            "properties",
            properties(
                property("key", scalarSchema("string")),
                property("family", scalarSchema("string")),
                property("variant", scalarSchema("string")),
                property("parameters", freeFormObjectSchema())
            )
        );
        return schema;
    }

    private static Map<String, Object> objectSchema(String... requiredKeys) {
        Map<String, Object> schema = new LinkedHashMap<String, Object>();
        schema.put("type", "object");
        if (requiredKeys != null && requiredKeys.length > 0) {
            schema.put("required", Arrays.<Object>asList(requiredKeys));
        }
        return schema;
    }

    private static Map<String, Object> freeFormObjectSchema() {
        Map<String, Object> schema = objectSchema();
        schema.put("additionalProperties", Boolean.TRUE);
        return schema;
    }

    private static Map<String, Object> scalarSchema(String type) {
        Map<String, Object> schema = new LinkedHashMap<String, Object>();
        schema.put("type", type);
        return schema;
    }

    private static Map<String, Object> scalarSchema(String type, String format) {
        Map<String, Object> schema = scalarSchema(type);
        schema.put("format", format);
        return schema;
    }

    private static Map<String, Object> stringConstSchema(String value) {
        Map<String, Object> schema = scalarSchema("string");
        schema.put("const", value);
        return schema;
    }

    private static Map<String, Object> stringEnumSchema(String... values) {
        Map<String, Object> schema = scalarSchema("string");
        schema.put("enum", Arrays.<Object>asList(values));
        return schema;
    }

    private static Map<String, Object> numberMapSchema() {
        Map<String, Object> schema = objectSchema();
        schema.put("additionalProperties", scalarSchema("number", "double"));
        return schema;
    }

    private static Map<String, Object> arraySchema(Object itemSchema) {
        Map<String, Object> schema = new LinkedHashMap<String, Object>();
        schema.put("type", "array");
        schema.put("items", itemSchema);
        return schema;
    }

    private static Map<String, Object> schemaRef(String componentName) {
        Map<String, Object> ref = new LinkedHashMap<String, Object>();
        ref.put("$ref", "#/components/schemas/" + componentName);
        return ref;
    }

    private static Map<String, Object> response(int status, String description, Object schema) {
        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("description", description);
        Map<String, Object> json = new LinkedHashMap<String, Object>();
        json.put("schema", schema);
        Map<String, Object> content = new LinkedHashMap<String, Object>();
        content.put("application/json", json);
        response.put("content", content);
        return response;
    }

    private static Map<String, Object> errorResponse(String description) {
        return response(0, description, schemaRef("ErrorResponse"));
    }

    private static Map<String, Object> jsonRequestBody(Object schema, boolean required) {
        Map<String, Object> requestBody = new LinkedHashMap<String, Object>();
        requestBody.put("required", Boolean.valueOf(required));
        Map<String, Object> json = new LinkedHashMap<String, Object>();
        json.put("schema", schema);
        Map<String, Object> content = new LinkedHashMap<String, Object>();
        content.put("application/json", json);
        requestBody.put("content", content);
        return requestBody;
    }

    private static Map<String, Object> singleMethod(String method, Map<String, Object> operation) {
        Map<String, Object> path = new LinkedHashMap<String, Object>();
        path.put(method, operation);
        return path;
    }

    private static Map<String, Object> properties(Map<String, Object>... items) {
        Map<String, Object> properties = new LinkedHashMap<String, Object>();
        for (Map<String, Object> item : items) {
            properties.putAll(item);
        }
        return properties;
    }

    private static Map<String, Object> property(String name, Object schema) {
        Map<String, Object> property = new LinkedHashMap<String, Object>();
        property.put(name, schema);
        return property;
    }

    private static String normalizeServerUrl(String serverUrl) {
        String value = serverUrl == null ? "" : serverUrl.trim();
        if (value.isEmpty()) {
            return "/";
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value.isEmpty() ? "/" : value;
    }

    private static String quoteJs(String value) {
        String safe = value == null ? "" : value.replace("\\", "\\\\").replace("'", "\\'");
        return "'" + safe + "'";
    }
}
