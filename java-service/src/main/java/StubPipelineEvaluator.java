import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class StubPipelineEvaluator implements PipelineEvaluator {
    private final ArtifactStore artifactStore;

    public StubPipelineEvaluator(ArtifactStore artifactStore) {
        this.artifactStore = artifactStore;
    }

    @Override
    public EvaluationResult evaluate(PipelineRequest request) throws Exception {
        if (request == null || request.pipeline == null || request.metrics == null) {
            throw new IllegalArgumentException("request, pipeline and metrics are required");
        }

        String fingerprint = computeFingerprint(request);
        Map<String, Double> canonical = computeCanonicalMetrics(request.pipeline, fingerprint);
        Map<String, Double> selected = new LinkedHashMap<String, Double>();

        for (String requestedMetric : request.metrics) {
            String key = normalizeMetricName(requestedMetric);
            Double value = canonical.get(key);
            if (value == null) {
                throw new IllegalArgumentException("unsupported metric: " + requestedMetric);
            }
            // Preserve response key exactly as requested by the client.
            selected.put(requestedMetric, value);
        }

        String pnml = buildStubPnml(request, fingerprint);
        return artifactStore.store(request, selected, pnml, fingerprint);
    }

    private String computeFingerprint(PipelineRequest request) {
        PipelineRequest.PipelineConfig pipeline = request.pipeline;
        String preKey = safe(pipeline.preprocessing != null ? pipeline.preprocessing.key : null);
        String preVariant = safe(pipeline.preprocessing != null ? pipeline.preprocessing.variant : null);
        String minerKey = safe(pipeline.miner != null ? pipeline.miner.key : null);
        String minerVariant = safe(pipeline.miner != null ? pipeline.miner.variant : null);

        return safe(request.log_path)
            + "|"
            + preKey
            + "|"
            + preVariant
            + "|"
            + minerKey
            + "|"
            + minerVariant
            + "|"
            + mapFingerprint(pipeline.preprocessing != null ? pipeline.preprocessing.parameters : null)
            + "|"
            + mapFingerprint(pipeline.miner != null ? pipeline.miner.parameters : null);
    }

    private Map<String, Double> computeCanonicalMetrics(PipelineRequest.PipelineConfig pipeline, String fingerprint) {
        int preParams = sizeOfMap(pipeline.preprocessing != null ? pipeline.preprocessing.parameters : null);
        int minerParams = sizeOfMap(pipeline.miner != null ? pipeline.miner.parameters : null);
        int totalParams = preParams + minerParams;

        double hash01 = (Math.abs(fingerprint.hashCode()) % 1000) / 1000.0;
        double complexityPenalty = Math.min(totalParams / 25.0, 1.0);

        double fitness = clamp01(0.55 + (0.35 * hash01));
        double precision = clamp01(0.50 + (0.25 * (1.0 - hash01)) - (0.05 * complexityPenalty));
        double simplicity = clamp01(0.92 - (0.50 * complexityPenalty));
        double generalisation = clamp01(0.45 + (0.30 * hash01) - (0.10 * complexityPenalty));

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", fitness);
        metrics.put("precision", precision);
        metrics.put("simplicity", simplicity);
        metrics.put("generalisation", generalisation);
        return metrics;
    }

    private String normalizeMetricName(String requestedMetric) {
        String metric = safe(requestedMetric).toLowerCase();
        if ("generalization".equals(metric)) {
            return "generalisation";
        }
        return metric;
    }

    private String buildStubPnml(PipelineRequest request, String fingerprint) {
        String preKey = safe(request.pipeline.preprocessing != null ? request.pipeline.preprocessing.key : null);
        String minerKey = safe(request.pipeline.miner != null ? request.pipeline.miner.key : null);
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            + "<pnml>\n"
            + "  <net id=\"stub-net\" type=\"http://www.pnml.org/version-2009/grammar/pnmlcoremodel\">\n"
            + "    <name><text>Stub net " + xmlEscape(fingerprint) + "</text></name>\n"
            + "    <toolspecific tool=\"minersweeper-stub\" version=\"1.0\">\n"
            + "      <preprocessing>" + xmlEscape(preKey) + "</preprocessing>\n"
            + "      <miner>" + xmlEscape(minerKey) + "</miner>\n"
            + "      <fingerprint>" + xmlEscape(fingerprint) + "</fingerprint>\n"
            + "    </toolspecific>\n"
            + "  </net>\n"
            + "</pnml>\n";
    }

    private static String xmlEscape(String value) {
        String text = safe(value);
        return text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;");
    }

    private static String mapFingerprint(Map<String, Object> map) {
        if (map == null || map.isEmpty()) {
            return "{}";
        }
        Map<String, Object> sorted = new TreeMap<String, Object>(map);
        return sorted.toString();
    }

    private static int sizeOfMap(Map<String, Object> map) {
        return map == null ? 0 : map.size();
    }

    private static String safe(String value) {
        return value == null ? "" : value.trim();
    }

    private static double clamp01(double value) {
        if (value < 0.0) {
            return 0.0;
        }
        if (value > 1.0) {
            return 1.0;
        }
        return value;
    }
}
