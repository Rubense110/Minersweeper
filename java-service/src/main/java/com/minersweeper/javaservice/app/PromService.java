package com.minersweeper.javaservice.app;

import com.minersweeper.javaservice.app.http.PromHttpHandlers;
import com.minersweeper.javaservice.app.logging.UnknownExtensionLogFilter;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PipelineEvaluator;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;

import static spark.Spark.get;
import static spark.Spark.post;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Paths;
import spark.Spark;

public class PromService {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final ArtifactStore ARTIFACT_STORE = new ArtifactStore(env("ARTIFACTS_ROOT", "/tmp/minersweeper-artifacts"));
    private static final PipelineEvaluator PIPELINE_EVALUATOR = buildPipelineEvaluator();
    private static final boolean VERBOSE_EXCEPTIONS = Boolean.parseBoolean(env("PROM_VERBOSE_EXCEPTIONS", "false"));
    private static final PromHttpHandlers HTTP_HANDLERS = new PromHttpHandlers(
        MAPPER,
        PIPELINE_EVALUATOR,
        ARTIFACT_STORE,
        VERBOSE_EXCEPTIONS
    );

    public static void main(String[] args) {
        UnknownExtensionLogFilter.install();

        int port = Integer.parseInt(env("PORT", "7070"));
        Spark.port(port);
        System.out.println("prom_service: listening on port " + port);

        get("/health", (req, res) -> {
            res.type("application/json");
            return "{\"status\":\"ok\"}";
        });

        post("/pipeline", (req, res) -> HTTP_HANDLERS.handlePipeline(req, res));
        post("/artifacts/bulk", (req, res) -> HTTP_HANDLERS.handleArtifactsBulk(req, res));
        post("/experiments/:experimentId/cancel", (req, res) -> HTTP_HANDLERS.handleCancel(req, res));
        post("/experiments/:experimentId/cleanup", (req, res) -> HTTP_HANDLERS.handleCleanup(req, res));
        get("/experiments/:experimentId/fingerprints", (req, res) -> HTTP_HANDLERS.handleExperimentFingerprints(req, res));
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return (value == null || value.trim().isEmpty()) ? fallback : value;
    }

    private static PipelineEvaluator buildPipelineEvaluator() {
        return new PromPipelineEvaluator(
            ARTIFACT_STORE,
            Paths.get(env("LOGS_ROOT", "pm_site/pm_app/logs"))
        );
    }

}
