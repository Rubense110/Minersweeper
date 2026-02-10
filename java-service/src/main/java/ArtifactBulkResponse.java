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
        public String pnml;
    }
}
