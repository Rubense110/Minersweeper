package com.minersweeper.javaservice.api.dto;

import java.util.Map;
import java.util.List;

public class PipelineResponse {
    public String experiment_id;
    public String evaluation_id;
    public String fingerprint;
    public Map<String, Double> metrics;
    public String metrics_status;
    public Integer model_schema_version;
    public Integer visible_transition_count;
    public Boolean is_feasible;
    public List<String> constraint_violations;

    public PipelineResponse() {}

    public PipelineResponse(String experiment_id, String evaluation_id, String fingerprint, Map<String, Double> metrics) {
        this(experiment_id, evaluation_id, fingerprint, metrics, null, null, null, null);
    }

    public PipelineResponse(
        String experiment_id,
        String evaluation_id,
        String fingerprint,
        Map<String, Double> metrics,
        Integer visible_transition_count,
        Boolean is_feasible,
        List<String> constraint_violations
    ) {
        this(
            experiment_id, evaluation_id, fingerprint, metrics, null,
            visible_transition_count, is_feasible, constraint_violations
        );
    }

    public PipelineResponse(
        String experiment_id,
        String evaluation_id,
        String fingerprint,
        Map<String, Double> metrics,
        Integer model_schema_version,
        Integer visible_transition_count,
        Boolean is_feasible,
        List<String> constraint_violations
    ) {
        this.experiment_id = experiment_id;
        this.evaluation_id = evaluation_id;
        this.fingerprint = fingerprint;
        this.metrics = metrics;
        this.model_schema_version = model_schema_version;
        this.visible_transition_count = visible_transition_count;
        this.is_feasible = is_feasible;
        this.constraint_violations = constraint_violations;
    }
}
