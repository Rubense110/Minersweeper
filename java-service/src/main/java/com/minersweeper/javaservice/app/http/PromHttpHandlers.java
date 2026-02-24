package com.minersweeper.javaservice.app.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.minersweeper.javaservice.app.logging.ServerErrorLogger;
import com.minersweeper.javaservice.app.validation.BadRequestException;
import com.minersweeper.javaservice.app.validation.RequestValidator;
import com.minersweeper.javaservice.api.dto.ArtifactBulkRequest;
import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.api.dto.PipelineResponse;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PipelineEvaluator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Consumer;

public final class PromHttpHandlers {
    private final ObjectMapper mapper;
    private final PipelineEvaluator pipelineEvaluator;
    private final ArtifactStore artifactStore;
    private final boolean verboseExceptions;

    public PromHttpHandlers(
        ObjectMapper mapper,
        PipelineEvaluator pipelineEvaluator,
        ArtifactStore artifactStore,
        boolean verboseExceptions
    ) {
        this.mapper = mapper;
        this.pipelineEvaluator = pipelineEvaluator;
        this.artifactStore = artifactStore;
        this.verboseExceptions = verboseExceptions;
    }

    public Object handlePipeline(spark.Request req, spark.Response res) throws Exception {
        ParsedPayload<PipelineRequest> parsed = parseAndValidate(
            req,
            res,
            PipelineRequest.class,
            RequestValidator::validatePipelineRequest
        );
        if (parsed.errorResponse != null) {
            return parsed.errorResponse;
        }
        PipelineRequest payload = parsed.payload;

        try {
            EvaluationResult evaluation = pipelineEvaluator.evaluate(payload);
            PipelineResponse response = new PipelineResponse(
                evaluation.experiment_id,
                evaluation.evaluation_id,
                evaluation.fingerprint,
                evaluation.metrics
            );
            return HttpResponses.respondJson(res, 200, response, mapper);
        } catch (IllegalArgumentException e) {
            ServerErrorLogger.log("invalid_request", e, verboseExceptions);
            return HttpResponses.respondError(res, 400, "invalid_request", HttpResponses.buildErrorMessage(e));
        } catch (Exception e) {
            ServerErrorLogger.log("evaluation_failed", e, verboseExceptions);
            return HttpResponses.respondError(res, 500, "evaluation_failed", HttpResponses.buildErrorMessage(e));
        }
    }

    public Object handleArtifactsBulk(spark.Request req, spark.Response res) throws Exception {
        ParsedPayload<ArtifactBulkRequest> parsed = parseAndValidate(
            req,
            res,
            ArtifactBulkRequest.class,
            RequestValidator::validateBulkArtifactsRequest
        );
        if (parsed.errorResponse != null) {
            return parsed.errorResponse;
        }
        ArtifactBulkRequest payload = parsed.payload;

        try {
            boolean includePnml = payload.include_pnml == null || payload.include_pnml.booleanValue();
            ArtifactBulkResponse response = artifactStore.readBulk(payload.experiment_id, payload.evaluation_ids, includePnml);
            return HttpResponses.respondJson(res, 200, response, mapper);
        } catch (IllegalArgumentException e) {
            return HttpResponses.respondError(res, 404, "not_found", e.getMessage());
        } catch (Exception e) {
            ServerErrorLogger.log("artifact_read_failed", e, verboseExceptions);
            return HttpResponses.respondError(res, 500, "artifact_read_failed", HttpResponses.buildErrorMessage(e));
        }
    }

    public Object handleCleanup(spark.Request req, spark.Response res) throws Exception {
        String experimentId = req.params(":experimentId");
        try {
            RequestValidator.validateExperimentIdPath(experimentId);
        } catch (BadRequestException e) {
            return HttpResponses.respondError(res, 400, "invalid_request", e.getMessage());
        }

        try {
            int deletedPaths = artifactStore.cleanupExperiment(experimentId);
            pipelineEvaluator.cleanupExperiment(experimentId);
            Map<String, Object> response = new LinkedHashMap<String, Object>();
            response.put("experiment_id", experimentId);
            response.put("deleted_paths", Integer.valueOf(deletedPaths));
            response.put("deleted", Boolean.valueOf(deletedPaths > 0));
            return HttpResponses.respondJson(res, 200, response, mapper);
        } catch (Exception e) {
            ServerErrorLogger.log("cleanup_failed", e, verboseExceptions);
            return HttpResponses.respondError(res, 500, "cleanup_failed", HttpResponses.buildErrorMessage(e));
        }
    }

    private <T> ParsedPayload<T> parseAndValidate(
        spark.Request req,
        spark.Response res,
        Class<T> payloadType,
        Consumer<T> validator
    ) {
        try {
            T payload = mapper.readValue(req.body(), payloadType);
            validator.accept(payload);
            return ParsedPayload.success(payload);
        } catch (BadRequestException e) {
            return ParsedPayload.error(HttpResponses.respondError(res, 400, "invalid_request", e.getMessage()));
        } catch (Exception e) {
            return ParsedPayload.error(HttpResponses.respondError(res, 400, "invalid_json", e.getMessage()));
        }
    }

    private static final class ParsedPayload<T> {
        private final T payload;
        private final Object errorResponse;

        private ParsedPayload(T payload, Object errorResponse) {
            this.payload = payload;
            this.errorResponse = errorResponse;
        }

        private static <T> ParsedPayload<T> success(T payload) {
            return new ParsedPayload<T>(payload, null);
        }

        private static <T> ParsedPayload<T> error(Object errorResponse) {
            return new ParsedPayload<T>(null, errorResponse);
        }
    }
}
