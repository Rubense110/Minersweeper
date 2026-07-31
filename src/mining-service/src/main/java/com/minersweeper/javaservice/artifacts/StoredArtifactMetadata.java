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
    public List<ArtifactBulkResponse.MarkingEntry> initial_marking;
    public List<List<ArtifactBulkResponse.MarkingEntry>> final_markings;
    public String pnml_file;
}
