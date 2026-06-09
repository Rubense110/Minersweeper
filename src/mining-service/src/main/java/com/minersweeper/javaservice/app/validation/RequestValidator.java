package com.minersweeper.javaservice.app.validation;

import com.minersweeper.javaservice.api.dto.ArtifactBulkRequest;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMetricCatalog;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMode;
import com.minersweeper.javaservice.evaluation.preprocessing.PreprocessingPipeline;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;

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
        if (payload.pipeline.miner == null) {
            throw new BadRequestException("pipeline.miner is required");
        }
        if (isBlank(payload.pipeline.miner.key)) {
            throw new BadRequestException("pipeline.miner.key is required");
        }
        if (payload.metrics == null || payload.metrics.isEmpty()) {
            throw new BadRequestException("metrics must contain at least one metric");
        }

        List<PipelineRequest.PreprocessingConfig> preprocessings = new ArrayList<PipelineRequest.PreprocessingConfig>();
        if (payload.pipeline.preprocessings != null && !payload.pipeline.preprocessings.isEmpty()) {
            preprocessings.addAll(payload.pipeline.preprocessings);
        } else if (payload.pipeline.preprocessing != null) {
            preprocessings.add(payload.pipeline.preprocessing);
        }
        for (int i = 0; i < preprocessings.size(); i++) {
            PipelineRequest.PreprocessingConfig preprocessing = preprocessings.get(i);
            if (preprocessing == null) {
                throw new BadRequestException("pipeline.preprocessings contains null entry at index " + i);
            }
            if (isBlank(preprocessing.key)) {
                throw new BadRequestException("pipeline.preprocessings[" + i + "].key is required");
            }
            preprocessing.key = preprocessing.key.trim().toLowerCase(Locale.ROOT);
            if (!PreprocessingPipeline.supportedKeys().contains(preprocessing.key)) {
                throw new BadRequestException("unsupported preprocessing key: " + preprocessing.key);
            }
            if (preprocessing.parameters == null) {
                preprocessing.parameters = new HashMap<String, Object>();
            }
            if (preprocessing.method == null) {
                preprocessing.method = "";
            }
            if (preprocessing.variant == null) {
                preprocessing.variant = "";
            }
        }
        payload.pipeline.preprocessings = preprocessings;
        payload.pipeline.preprocessing = preprocessings.isEmpty() ? null : preprocessings.get(0);

        if (payload.pipeline.miner.parameters == null) {
            payload.pipeline.miner.parameters = new HashMap<String, Object>();
        }
        if (payload.excluded_miners == null) {
            payload.excluded_miners = new ArrayList<String>();
        }
        ConformanceMode conformanceMode;
        try {
            conformanceMode = ConformanceMode.resolve(payload.conformance_mode);
        } catch (IllegalArgumentException error) {
            throw new BadRequestException(error.getMessage());
        }
        payload.conformance_mode = conformanceMode.key();
        try {
            List<String> canonicalMetrics = ConformanceMetricCatalog.canonicalizeRequestedMetrics(
                payload.metrics,
                conformanceMode
            );
            payload.metrics = canonicalMetrics;
        } catch (IllegalArgumentException error) {
            throw new BadRequestException(error.getMessage());
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
