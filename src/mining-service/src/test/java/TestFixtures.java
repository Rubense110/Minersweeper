import com.minersweeper.javaservice.api.dto.PipelineRequest;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class TestFixtures {
    private TestFixtures() {}

    static Path createTinyLog(Path dir, String filename) throws IOException {
        String xes = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            + "<log xes.version=\"1.0\" xes.features=\"nested-attributes\" xmlns=\"http://www.xes-standard.org/\">\n"
            + "  <extension name=\"Concept\" prefix=\"concept\" uri=\"http://www.xes-standard.org/concept.xesext\"/>\n"
            + "  <extension name=\"Lifecycle\" prefix=\"lifecycle\" uri=\"http://www.xes-standard.org/lifecycle.xesext\"/>\n"
            + "  <classifier name=\"Event Name\" keys=\"concept:name\"/>\n"
            + "  <trace>\n"
            + "    <string key=\"concept:name\" value=\"Case1\"/>\n"
            + "    <event><string key=\"concept:name\" value=\"A\"/><string key=\"lifecycle:transition\" value=\"complete\"/></event>\n"
            + "    <event><string key=\"concept:name\" value=\"B\"/><string key=\"lifecycle:transition\" value=\"complete\"/></event>\n"
            + "    <event><string key=\"concept:name\" value=\"C\"/><string key=\"lifecycle:transition\" value=\"complete\"/></event>\n"
            + "  </trace>\n"
            + "  <trace>\n"
            + "    <string key=\"concept:name\" value=\"Case2\"/>\n"
            + "    <event><string key=\"concept:name\" value=\"A\"/><string key=\"lifecycle:transition\" value=\"complete\"/></event>\n"
            + "    <event><string key=\"concept:name\" value=\"C\"/><string key=\"lifecycle:transition\" value=\"complete\"/></event>\n"
            + "  </trace>\n"
            + "</log>\n";
        Path file = dir.resolve(filename);
        Files.write(file, xes.getBytes(StandardCharsets.UTF_8));
        return file;
    }

    static List<String> defaultMetrics() {
        return Arrays.asList("fitness", "precision", "simplicity", "generalisation");
    }

    static PipelineRequest buildRequest(
        String experimentId,
        String logPath,
        PipelineRequest.PreprocessingConfig preprocessing,
        PipelineRequest.MinerConfig miner,
        List<String> metrics
    ) {
        PipelineRequest request = new PipelineRequest();
        request.experiment_id = experimentId;
        request.log_path = logPath;
        request.metrics = metrics;

        PipelineRequest.PipelineConfig pipeline = new PipelineRequest.PipelineConfig();
        pipeline.preprocessing = preprocessing;
        pipeline.miner = miner;
        request.pipeline = pipeline;

        return request;
    }

    static PipelineRequest.PreprocessingConfig matrixFilter() {
        return preprocessing(
            "matrix_filter",
            "Matrix Filtering",
            "Conditional Probabilities (MF)",
            mapOf(
                "probability_of_removal_mf", Double.valueOf(0.15),
                "subsequence_length_mf", Integer.valueOf(2)
            )
        );
    }

    static PipelineRequest.PreprocessingConfig repairLogFilter() {
        return preprocessing(
            "repair_log_filter",
            "Repair Log Filter",
            "Repair Log Filter (RLF)",
            mapOf(
                "probability_of_removal_rl", Double.valueOf(0.15),
                "subsequence_length_rl", Integer.valueOf(2)
            )
        );
    }

    static PipelineRequest.PreprocessingConfig variantFilter() {
        return preprocessing(
            "variant_filter",
            "Variant Log Filter",
            "Variant Log Filter",
            mapOf("keep_threshold_vf", Integer.valueOf(50))
        );
    }

    static PipelineRequest.PreprocessingConfig projectionFilter() {
        return preprocessing(
            "projection_filter",
            "Projection Log Filter",
            "Projection Log Filter",
            mapOf("keep_threshold_p", Integer.valueOf(50))
        );
    }

    static List<PipelineRequest.PreprocessingConfig> allPreprocessings() {
        return Arrays.asList(
            matrixFilter(),
            repairLogFilter(),
            variantFilter(),
            projectionFilter()
        );
    }

    static PipelineRequest.MinerConfig alphaClassic() {
        return miner(
            "alpha",
            "alpha",
            "Alpha",
            mapOf("alpha_version", "CLASSIC")
        );
    }

    static PipelineRequest.MinerConfig inductiveImf() {
        return miner(
            "inductive",
            "inductive",
            "Inductive Miner - infrequent (IMf)",
            mapOf(
                "noise_threshold", Double.valueOf(0.2),
                "is_debug", Boolean.FALSE,
                "use_multithreading", Boolean.TRUE
            )
        );
    }

    static PipelineRequest.MinerConfig heuristicsHm() {
        return miner(
            "heuristics",
            "heuristics",
            "Heuristics Miner",
            mapOf(
                "relative_to_best_threshold", Double.valueOf(0.05),
                "positive_observation_threshold", Integer.valueOf(1),
                "dependency_threshold", Double.valueOf(0.90),
                "l1l_threshold", Double.valueOf(0.90),
                "l2l_threshold", Double.valueOf(0.90),
                "long_distance_threshold", Double.valueOf(0.90),
                "dependency_divisor", Integer.valueOf(1),
                "and_threshold", Double.valueOf(0.10),
                "extra_info", Boolean.FALSE,
                "use_all_connected_heuristics", Boolean.TRUE,
                "use_long_distance_dependency", Boolean.FALSE,
                "check_best_against_l2l", Boolean.TRUE
            )
        );
    }

    static PipelineRequest.MinerConfig splitMiner() {
        return miner(
            "split",
            "split",
            "Split Miner",
            mapOf(
                "epsilon", Double.valueOf(0.5),
                "eta", Double.valueOf(0.5)
            )
        );
    }

    static PipelineRequest.MinerConfig ilpDefault() {
        return miner(
            "ilp",
            "ilp",
            "Petri Net ILP",
            mapOf(
                "solver_type", "JAVAILP_LPSOLVE",
                "search_type", "PER_CD",
                "separate_initial_places", Boolean.TRUE,
                "license_dir", "c:\\ILOG\\ILM"
            )
        );
    }

    static PipelineRequest.MinerConfig hybridIlpDefault() {
        return miner(
            "hybrid_ilp",
            "hybrid_ilp",
            "Hybrid ILPMiner",
            mapOf(
                "lp_objective", "Minimize Arcs",
                "lp_variable_type", "Two variables per event",
                "lp_filter", "None",
                "discovery_strategy", "Random"
            )
        );
    }

    static List<PipelineRequest.MinerConfig> allMinerFamilies() {
        return Arrays.asList(
            alphaClassic(),
            inductiveImf(),
            heuristicsHm(),
            splitMiner(),
            ilpDefault(),
            hybridIlpDefault()
        );
    }

    static void assertMetricsRange(Map<String, Double> metrics, List<String> expectedKeys) {
        for (String key : expectedKeys) {
            if (!metrics.containsKey(key)) {
                throw new AssertionError("missing metric key: " + key + " in " + metrics.keySet());
            }
            Double value = metrics.get(key);
            if (value == null || value.doubleValue() < 0.0 || value.doubleValue() > 1.0) {
                throw new AssertionError("metric out of [0,1] for key " + key + ": " + value);
            }
        }
    }

    private static PipelineRequest.PreprocessingConfig preprocessing(
        String key,
        String method,
        String variant,
        Map<String, Object> params
    ) {
        PipelineRequest.PreprocessingConfig cfg = new PipelineRequest.PreprocessingConfig();
        cfg.key = key;
        cfg.method = method;
        cfg.variant = variant;
        cfg.parameters = params;
        return cfg;
    }

    private static PipelineRequest.MinerConfig miner(
        String key,
        String family,
        String variant,
        Map<String, Object> params
    ) {
        PipelineRequest.MinerConfig cfg = new PipelineRequest.MinerConfig();
        cfg.key = key;
        cfg.family = family;
        cfg.variant = variant;
        cfg.parameters = params;
        return cfg;
    }

    private static Map<String, Object> mapOf(Object... values) {
        if (values.length % 2 != 0) {
            throw new IllegalArgumentException("mapOf requires key/value pairs");
        }
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        for (int i = 0; i < values.length; i += 2) {
            out.put(String.valueOf(values[i]), values[i + 1]);
        }
        return out;
    }
}
