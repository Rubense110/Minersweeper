import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.Test;

public class StubPipelineEvaluatorTest {

    @Test
    public void evaluateReturnsRequestedMetricsAndStoresArtifact() throws Exception {
        Path tmp = Files.createTempDirectory("stub-evaluator-test");
        ArtifactStore store = new ArtifactStore(tmp.toString());
        StubPipelineEvaluator evaluator = new StubPipelineEvaluator(store);

        List<String> requestedMetrics = Arrays.asList(
            "fitness",
            "precision",
            "simplicity",
            "generalization"
        );

        PipelineRequest request = TestFixtures.buildRequest(
            "run_stub",
            "/tmp/log.xes",
            TestFixtures.matrixFilter(),
            TestFixtures.inductiveImf(),
            requestedMetrics
        );

        EvaluationResult result = evaluator.evaluate(request);

        assertEquals("run_stub", result.experiment_id);
        assertNotNull(result.evaluation_id);
        assertNotNull(result.fingerprint);
        assertTrue(result.fingerprint.contains("matrix_filter"));
        assertTrue(result.fingerprint.contains("inductive"));

        assertEquals(4, result.metrics.size());
        assertTrue(result.metrics.containsKey("generalization"));
        TestFixtures.assertMetricsRange(result.metrics, requestedMetrics);

        ArtifactBulkResponse bulk = store.readBulk("run_stub", Arrays.asList(result.evaluation_id), true);
        assertEquals(1, bulk.artifacts.size());
        assertTrue(bulk.artifacts.get(0).pnml.contains("stub-net"));
    }

    @Test
    public void evaluateIsStableForEquivalentMapsWithDifferentInsertionOrder() throws Exception {
        Path tmp = Files.createTempDirectory("stub-evaluator-order-test");
        ArtifactStore store = new ArtifactStore(tmp.toString());
        StubPipelineEvaluator evaluator = new StubPipelineEvaluator(store);

        PipelineRequest.PreprocessingConfig preprocessingA = TestFixtures.matrixFilter();
        PipelineRequest.MinerConfig minerA = TestFixtures.inductiveImf();

        Map<String, Object> preParamsB = new LinkedHashMap<String, Object>();
        preParamsB.put("subsequence_length_mf", Integer.valueOf(2));
        preParamsB.put("probability_of_removal_mf", Double.valueOf(0.15));
        PipelineRequest.PreprocessingConfig preprocessingB = new PipelineRequest.PreprocessingConfig();
        preprocessingB.key = preprocessingA.key;
        preprocessingB.method = preprocessingA.method;
        preprocessingB.variant = preprocessingA.variant;
        preprocessingB.parameters = preParamsB;

        Map<String, Object> minerParamsB = new LinkedHashMap<String, Object>();
        minerParamsB.put("use_multithreading", Boolean.TRUE);
        minerParamsB.put("noise_threshold", Double.valueOf(0.2));
        minerParamsB.put("is_debug", Boolean.FALSE);
        PipelineRequest.MinerConfig minerB = new PipelineRequest.MinerConfig();
        minerB.key = minerA.key;
        minerB.family = minerA.family;
        minerB.variant = minerA.variant;
        minerB.parameters = minerParamsB;

        List<String> metrics = TestFixtures.defaultMetrics();

        PipelineRequest reqA = TestFixtures.buildRequest("run_a", "/tmp/log.xes", preprocessingA, minerA, metrics);
        PipelineRequest reqB = TestFixtures.buildRequest("run_b", "/tmp/log.xes", preprocessingB, minerB, metrics);

        EvaluationResult resA = evaluator.evaluate(reqA);
        EvaluationResult resB = evaluator.evaluate(reqB);

        assertEquals(resA.fingerprint, resB.fingerprint);
        assertEquals(resA.metrics, resB.metrics);
    }

    @Test
    public void evaluateThrowsForUnsupportedMetric() throws Exception {
        Path tmp = Files.createTempDirectory("stub-evaluator-error-test");
        ArtifactStore store = new ArtifactStore(tmp.toString());
        StubPipelineEvaluator evaluator = new StubPipelineEvaluator(store);

        PipelineRequest request = TestFixtures.buildRequest(
            "run_stub_error",
            "/tmp/log.xes",
            TestFixtures.matrixFilter(),
            TestFixtures.alphaClassic(),
            Arrays.asList("fitness", "not_a_metric")
        );

        try {
            evaluator.evaluate(request);
            fail("Expected IllegalArgumentException for unsupported metric");
        } catch (IllegalArgumentException expected) {
            assertTrue(expected.getMessage().contains("unsupported metric"));
        }
    }
}
