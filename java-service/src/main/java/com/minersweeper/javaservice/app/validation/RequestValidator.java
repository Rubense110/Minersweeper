package com.minersweeper.javaservice.app.validation;

import com.minersweeper.javaservice.api.dto.ArtifactBulkRequest;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMetricCatalog;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

public final class RequestValidator {
    private RequestValidator() {}

    public static void validatePipelineRequest(PipelineRequest payload) {
        if (payload == null) {
            throw new BadRequestException("request body is required");
        }
        if (isBlank(payload.experiment_id)) {
            throw new BadRequestException("experiment_id is required");
        }
        if (isBlank(payload.log_path)) {
            throw new BadRequestException("log_path is required");
        }
        if (payload.pipeline == null) {
            throw new BadRequestException("pipeline is required");
        }
        if (payload.pipeline.preprocessing == null) {
            throw new BadRequestException("pipeline.preprocessing is required");
        }
        if (payload.pipeline.miner == null) {
            throw new BadRequestException("pipeline.miner is required");
        }
        if (isBlank(payload.pipeline.preprocessing.key)) {
            throw new BadRequestException("pipeline.preprocessing.key is required");
        }
        if (isBlank(payload.pipeline.miner.key)) {
            throw new BadRequestException("pipeline.miner.key is required");
        }
        if (payload.metrics == null || payload.metrics.isEmpty()) {
            throw new BadRequestException("metrics must contain at least one metric");
        }
        if (payload.pipeline.preprocessing.parameters == null) {
            payload.pipeline.preprocessing.parameters = new HashMap<String, Object>();
        }
        if (payload.pipeline.miner.parameters == null) {
            payload.pipeline.miner.parameters = new HashMap<String, Object>();
        }
        if (payload.excluded_miners == null) {
            payload.excluded_miners = new ArrayList<String>();
        }
        Map<String, ?> metricsByKey = ConformanceMetricCatalog.metricsByKey();
        for (String metric : payload.metrics) {
            if (isBlank(metric)) {
                throw new BadRequestException("metrics cannot contain empty values");
            }
            if (!metricsByKey.containsKey(metric)) {
                throw new BadRequestException("unsupported metric: " + metric);
            }
        }
    }

    public static void validateBulkArtifactsRequest(ArtifactBulkRequest payload) {
        if (payload == null) {
            throw new BadRequestException("request body is required");
        }
        if (isBlank(payload.experiment_id)) {
            throw new BadRequestException("experiment_id is required");
        }
        if (payload.evaluation_ids == null || payload.evaluation_ids.isEmpty()) {
            throw new BadRequestException("evaluation_ids must contain at least one value");
        }
        for (String evaluationId : payload.evaluation_ids) {
            if (isBlank(evaluationId)) {
                throw new BadRequestException("evaluation_ids cannot contain empty values");
            }
        }
    }

    public static void validateExperimentIdPath(String experimentId) {
        if (isBlank(experimentId)) {
            throw new BadRequestException("experimentId path parameter is required");
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
