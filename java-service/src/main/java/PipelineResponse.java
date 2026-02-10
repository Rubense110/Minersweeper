import java.util.Map;

public class PipelineResponse {
    public String experiment_id;
    public String evaluation_id;
    public String fingerprint;
    public Map<String, Double> metrics;

    public PipelineResponse() {}

    public PipelineResponse(String experiment_id, String evaluation_id, String fingerprint, Map<String, Double> metrics) {
        this.experiment_id = experiment_id;
        this.evaluation_id = evaluation_id;
        this.fingerprint = fingerprint;
        this.metrics = metrics;
    }
}
