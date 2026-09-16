import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.Test;

public class ArtifactStoreTest {

    @Test
    public void storeAndReadBulkWithPnml() throws Exception {
        Path tmp = Files.createTempDirectory("artifact-store-test");
        ArtifactStore store = new ArtifactStore(tmp.toString());

        PipelineRequest request = TestFixtures.buildRequest(
            "run_001",
            "/tmp/log.xes",
            TestFixtures.matrixFilter(),
            TestFixtures.inductiveImf(),
            TestFixtures.defaultMetrics()
        );

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", Double.valueOf(0.8));
        metrics.put("precision", Double.valueOf(0.6));
        metrics.put("simplicity", Double.valueOf(0.7));
        metrics.put("generalisation", Double.valueOf(0.5));

        ArtifactBulkResponse.MarkingEntry initial = new ArtifactBulkResponse.MarkingEntry("p_start", 1);
        ArtifactBulkResponse.MarkingEntry fin = new ArtifactBulkResponse.MarkingEntry("p_end", 1);
        EvaluationResult evaluation = store.store(
            request,
            metrics,
            "<pnml/>",
            "fingerprint-1",
            Arrays.asList(initial),
            Arrays.asList(Arrays.asList(fin))
        );

        ArtifactBulkResponse bulk = store.readBulk(
            "run_001",
            Arrays.asList(evaluation.evaluation_id),
            true
        );

        assertEquals("run_001", bulk.experiment_id);
        assertEquals(1, bulk.artifacts.size());
        ArtifactBulkResponse.ArtifactEntry entry = bulk.artifacts.get(0);
        assertEquals(evaluation.evaluation_id, entry.evaluation_id);
        assertEquals("fingerprint-1", entry.fingerprint);
        assertEquals("run_001", entry.experiment_id);
        assertEquals("/tmp/log.xes", entry.log_path);
        assertNotNull(entry.pipeline);
        assertNotNull(entry.metrics);
        assertEquals(Double.valueOf(0.8), entry.metrics.get("fitness"));
        assertEquals(1, entry.initial_marking.size());
        assertEquals("p_start", entry.initial_marking.get(0).place_id);
        assertEquals(1, entry.initial_marking.get(0).tokens);
        assertEquals(1, entry.final_markings.size());
        assertEquals("p_end", entry.final_markings.get(0).get(0).place_id);
        assertEquals(1, entry.final_markings.get(0).get(0).tokens);
        assertTrue(entry.pnml.contains("pnml"));
    }

    @Test
    public void readBulkWithoutPnmlOmitsContent() throws Exception {
        Path tmp = Files.createTempDirectory("artifact-store-test-no-pnml");
        ArtifactStore store = new ArtifactStore(tmp.toString());

        PipelineRequest request = TestFixtures.buildRequest(
            "run_002",
            "/tmp/log.xes",
            TestFixtures.variantFilter(),
            TestFixtures.alphaClassic(),
            TestFixtures.defaultMetrics()
        );

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", Double.valueOf(0.8));

        EvaluationResult evaluation = store.store(request, metrics, "<pnml/>", "fingerprint-2");
        ArtifactBulkResponse bulk = store.readBulk(
            "run_002",
            Arrays.asList(evaluation.evaluation_id),
            false
        );

        assertEquals(1, bulk.artifacts.size());
        assertNull(bulk.artifacts.get(0).pnml);
    }

    @Test
    public void storesV2SemanticArtifactWithoutDroppingEmptyMarkings() throws Exception {
        Path tmp = Files.createTempDirectory("artifact-store-v2");
        ArtifactStore store = new ArtifactStore(tmp.toString());
        PipelineRequest request = TestFixtures.buildRequest(
            "run_v2", "/tmp/log.xes", TestFixtures.matrixFilter(), TestFixtures.inductiveImf(), TestFixtures.defaultMetrics()
        );
        ArtifactBulkResponse.MarkingEntry finalEntry = new ArtifactBulkResponse.MarkingEntry("p_end", 3);
        ArtifactBulkResponse.TransitionEntry transition = new ArtifactBulkResponse.TransitionEntry("t1", "tau", false);
        EvaluationResult evaluation = store.store(
            request,
            new LinkedHashMap<String, Double>(),
            "<pnml/>",
            "semantic-fingerprint",
            Integer.valueOf(2),
            Integer.valueOf(0),
            Boolean.FALSE,
            Arrays.asList("NO_VISIBLE_TRANSITIONS"),
            Arrays.<ArtifactBulkResponse.MarkingEntry>asList(),
            Arrays.asList(finalEntry),
            Arrays.asList(Arrays.<ArtifactBulkResponse.MarkingEntry>asList(), Arrays.asList(finalEntry)),
            Arrays.asList(transition)
        );

        ArtifactBulkResponse.ArtifactEntry entry = store.readBulk("run_v2", Arrays.asList(evaluation.evaluation_id), false).artifacts.get(0);
        assertEquals(Integer.valueOf(2), evaluation.model_schema_version);
        assertEquals(Integer.valueOf(2), entry.model_schema_version);
        assertEquals(Integer.valueOf(0), entry.visible_transition_count);
        assertFalse(entry.is_feasible.booleanValue());
        assertEquals(Arrays.asList("NO_VISIBLE_TRANSITIONS"), entry.constraint_violations);
        assertTrue(entry.initial_marking.isEmpty());
        assertEquals(3, entry.final_marking.get(0).tokens);
        assertTrue(entry.final_markings.get(0).isEmpty());
        assertFalse(entry.transitions.get(0).invisible);
        assertEquals("tau", entry.transitions.get(0).label);
    }

    @Test
    public void cleanupExperimentDeletesStoredFiles() throws Exception {
        Path tmp = Files.createTempDirectory("artifact-store-test-cleanup");
        ArtifactStore store = new ArtifactStore(tmp.toString());

        PipelineRequest request = TestFixtures.buildRequest(
            "run_cleanup",
            "/tmp/log.xes",
            TestFixtures.projectionFilter(),
            TestFixtures.heuristicsHm(),
            TestFixtures.defaultMetrics()
        );

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", Double.valueOf(0.9));
        store.store(request, metrics, "<pnml/>", "fp-cleanup");

        int deletedPaths = store.cleanupExperiment("run_cleanup");
        assertTrue(deletedPaths > 0);

        Path experimentDir = tmp.resolve("run_cleanup");
        assertFalse(Files.exists(experimentDir));
    }

    @Test
    public void readBulkThrowsWhenEvaluationMissing() throws Exception {
        Path tmp = Files.createTempDirectory("artifact-store-test-missing");
        ArtifactStore store = new ArtifactStore(tmp.toString());

        try {
            store.readBulk("run_missing", Arrays.asList("does-not-exist"), true);
            fail("Expected IllegalArgumentException for unknown evaluation_id");
        } catch (IllegalArgumentException expected) {
            assertTrue(expected.getMessage().contains("evaluation_id not found"));
        }
    }

}
