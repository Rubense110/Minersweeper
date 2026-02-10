import java.util.Map;

public class StoredArtifactMetadata {
    public String experiment_id;
    public String evaluation_id;
    public String fingerprint;
    public String log_path;
    public long created_at_epoch_ms;
    public Map<String, Double> metrics;
    public PipelineRequest.PipelineConfig pipeline;
    public String pnml_file;
}
