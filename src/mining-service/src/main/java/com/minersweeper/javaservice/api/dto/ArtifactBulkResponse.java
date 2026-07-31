package com.minersweeper.javaservice.api.dto;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ArtifactBulkResponse {
    public String experiment_id;
    public List<ArtifactEntry> artifacts = new ArrayList<ArtifactEntry>();

    public static class ArtifactEntry {
        public String experiment_id;
        public String evaluation_id;
        public String fingerprint;
        public String log_path;
        public long created_at_epoch_ms;
        public Map<String, Double> metrics;
        public PipelineRequest.PipelineConfig pipeline;
        public List<MarkingEntry> initial_marking;
        public List<List<MarkingEntry>> final_markings;
        public String pnml;
    }

    public static class MarkingEntry {
        public String place_id;
        public int tokens;

        public MarkingEntry() {}

        public MarkingEntry(String place_id, int tokens) {
            this.place_id = place_id;
            this.tokens = tokens;
        }
    }
}
