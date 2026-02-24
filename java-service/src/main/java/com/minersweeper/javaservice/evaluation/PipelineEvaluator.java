package com.minersweeper.javaservice.evaluation;

import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;


public interface PipelineEvaluator {
    EvaluationResult evaluate(PipelineRequest request) throws Exception;

    default void cleanupExperiment(String experimentId) {
        // Optional hook for evaluator-level in-memory resources.
    }
}
