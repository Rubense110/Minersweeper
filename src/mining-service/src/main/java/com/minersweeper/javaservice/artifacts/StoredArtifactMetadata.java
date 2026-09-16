package com.minersweeper.javaservice.artifacts;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;

import java.util.List;
import java.util.Map;

public class StoredArtifactMetadata {
    public String experiment_id;
    public String evaluation_id;
    public String fingerprint;
    public String log_path;
    public long created_at_epoch_ms;
    public Map<String, Double> metrics;
    public PipelineRequest.PipelineConfig pipeline;
    public Integer model_schema_version;
    public Integer visible_transition_count;
    public Boolean is_feasible;
    public List<String> constraint_violations;
    public List<ArtifactBulkResponse.MarkingEntry> initial_marking;
    public List<ArtifactBulkResponse.MarkingEntry> final_marking;
    public List<List<ArtifactBulkResponse.MarkingEntry>> final_markings;
    public List<ArtifactBulkResponse.TransitionEntry> transitions;
    public String pnml_file;
}
