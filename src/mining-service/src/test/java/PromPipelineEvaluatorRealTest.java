import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;

import java.io.File;
import java.io.ByteArrayInputStream;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.xml.parsers.DocumentBuilderFactory;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public class PromPipelineEvaluatorRealTest {
    private static Path workDir;
    private static Path logFile;
    private static ArtifactStore store;
    private static PromPipelineEvaluator evaluator;

    @BeforeClass
    public static void setup() throws Exception {
        String runFlag = System.getenv("RUN_REAL_PROM_TESTS");
        Assume.assumeTrue(
            "Set RUN_REAL_PROM_TESTS=1 to run real ProM evaluator tests",
            "1".equals(runFlag)
        );

        Path promHome = resolvePromHome();
        Assume.assumeTrue("PROM_HOME not found: " + promHome, Files.isDirectory(promHome));

        Path lpsolveDir = findLpSolveNativeDir(promHome);
        Assume.assumeTrue("lpsolve native directory not found under: " + promHome, lpsolveDir != null);
        appendJavaLibraryPath(lpsolveDir.toAbsolutePath().toString());

        workDir = Files.createTempDirectory("prom-real-evaluator-test");
        logFile = TestFixtures.createTinyLog(workDir, "tiny-test-log.xes");

        store = new ArtifactStore(workDir.resolve("artifacts").toString());
        evaluator = new PromPipelineEvaluator(store, workDir);
    }

    @Test(timeout = 600000)
    public void allMinerFamiliesProduceMetricsAndArtifacts() throws Exception {
        List<PipelineRequest.MinerConfig> miners = TestFixtures.allMinerFamilies();

        for (PipelineRequest.MinerConfig miner : miners) {
            String experimentId = "real_miner_" + miner.key;
            PipelineRequest request = TestFixtures.buildRequest(
                experimentId,
                logFile.toString(),
                TestFixtures.matrixFilter(),
                miner,
                TestFixtures.defaultMetrics()
            );

            EvaluationResult result = evaluator.evaluate(request);
            assertEquals(experimentId, result.experiment_id);
            assertNotNull(result.evaluation_id);
            assertTrue(result.fingerprint.contains(miner.key));
            assertEquals(Integer.valueOf(2), result.model_schema_version);
            TestFixtures.assertMetricsRange(result.metrics, TestFixtures.defaultMetrics());

            ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
            assertEquals(1, bulk.artifacts.size());
            ArtifactBulkResponse.ArtifactEntry artifact = bulk.artifacts.get(0);
            assertEquals(miner.key, artifact.pipeline.miner.key);
            assertTrue(artifact.pnml.contains("pnml"));
            assertV2Semantics(artifact);
        }
    }

    @Test(timeout = 600000)
    public void allPreprocessingsAreAcceptedAndPersisted() throws Exception {
        List<PipelineRequest.PreprocessingConfig> preprocessings = TestFixtures.allPreprocessings();

        for (PipelineRequest.PreprocessingConfig preprocessing : preprocessings) {
            String experimentId = "real_pre_" + preprocessing.key;
            PipelineRequest request = TestFixtures.buildRequest(
                experimentId,
                logFile.toString(),
                preprocessing,
                TestFixtures.inductiveImf(),
                TestFixtures.defaultMetrics()
            );

            EvaluationResult result = evaluator.evaluate(request);
            assertEquals(experimentId, result.experiment_id);
            assertTrue(result.fingerprint.contains(preprocessing.key));
            TestFixtures.assertMetricsRange(result.metrics, TestFixtures.defaultMetrics());

            ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
            assertEquals(1, bulk.artifacts.size());
            assertEquals(preprocessing.key, bulk.artifacts.get(0).pipeline.preprocessing.key);
            assertTrue(bulk.artifacts.get(0).pnml.contains("pnml"));
        }
    }

    private static Path resolvePromHome() {
        String env = System.getenv("PROM_HOME");
        if (env != null && !env.trim().isEmpty()) {
            return Paths.get(env.trim()).toAbsolutePath().normalize();
        }
        Path javaServiceDir = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        return javaServiceDir.resolve("..").resolve("..").resolve("tools").resolve("prom-lite-1.4-all-platforms").normalize();
    }

    private static void assertV2Semantics(ArtifactBulkResponse.ArtifactEntry artifact) throws Exception {
        assertEquals(Integer.valueOf(2), artifact.model_schema_version);
        assertNotNull(artifact.initial_marking);
        assertNotNull(artifact.final_marking);
        assertNotNull(artifact.final_markings);
        assertTrue("at least one real final marking is required", !artifact.final_markings.isEmpty());
        assertMarkingsEqual(artifact.final_marking, artifact.final_markings.get(0));

        Set<String> placeIds = pnmlNodeIds(artifact.pnml, "place");
        assertMarking(artifact.initial_marking, placeIds);
        assertMarking(artifact.final_marking, placeIds);
        for (List<ArtifactBulkResponse.MarkingEntry> marking : artifact.final_markings) {
            assertMarking(marking, placeIds);
        }

        assertNotNull(artifact.transitions);
        Set<String> transitionIds = pnmlNodeIds(artifact.pnml, "transition");
        assertEquals(transitionIds.size(), artifact.transitions.size());
        int actualVisibleCount = 0;
        for (ArtifactBulkResponse.TransitionEntry transition : artifact.transitions) {
            assertTrue("transition ID must exist in PNML", transitionIds.contains(transition.id));
            if (!transition.invisible) {
                actualVisibleCount++;
            }
        }
        assertEquals(Integer.valueOf(actualVisibleCount), artifact.visible_transition_count);
        assertNotNull(artifact.is_feasible);
        assertEquals(Boolean.valueOf(actualVisibleCount > 0), artifact.is_feasible);
        assertNotNull(artifact.constraint_violations);
        assertEquals(
            actualVisibleCount > 0 ? Arrays.<String>asList() : Arrays.asList("NO_VISIBLE_TRANSITIONS"),
            artifact.constraint_violations
        );
    }

    private static void assertMarking(
        List<ArtifactBulkResponse.MarkingEntry> marking,
        Set<String> placeIds
    ) {
        assertNotNull(marking);
        for (ArtifactBulkResponse.MarkingEntry entry : marking) {
            assertTrue("marking place ID must exist in PNML", placeIds.contains(entry.place_id));
            assertTrue("marking multiplicity must be positive", entry.tokens > 0);
        }
    }

    private static void assertMarkingsEqual(
        List<ArtifactBulkResponse.MarkingEntry> expected,
        List<ArtifactBulkResponse.MarkingEntry> actual
    ) {
        assertEquals(expected.size(), actual.size());
        for (int index = 0; index < expected.size(); index++) {
            assertEquals(expected.get(index).place_id, actual.get(index).place_id);
            assertEquals(expected.get(index).tokens, actual.get(index).tokens);
        }
    }

    private static Set<String> pnmlNodeIds(String pnml, String nodeName) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        Document document = factory.newDocumentBuilder().parse(
            new ByteArrayInputStream(pnml.getBytes(StandardCharsets.UTF_8))
        );
        NodeList nodes = document.getElementsByTagNameNS("*", nodeName);
        if (nodes.getLength() == 0) {
            nodes = document.getElementsByTagName(nodeName);
        }
        Set<String> ids = new HashSet<String>();
        for (int index = 0; index < nodes.getLength(); index++) {
            ids.add(((Element) nodes.item(index)).getAttribute("id"));
        }
        return ids;
    }

    private static Path findLpSolveNativeDir(Path promHome) throws Exception {
        try (java.util.stream.Stream<Path> stream = Files.walk(promHome)) {
            Path lib = stream
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().equals("liblpsolve55.so"))
                .findFirst()
                .orElse(null);
            return lib == null ? null : lib.getParent();
        }
    }

    // Makes JNI libraries discoverable for tests that load lpsolve at runtime.
    private static void appendJavaLibraryPath(String nativeDir) throws Exception {
        String current = System.getProperty("java.library.path", "");
        if (!current.contains(nativeDir)) {
            String updated = nativeDir + File.pathSeparator + current;
            System.setProperty("java.library.path", updated);
        }

        Field sysPaths = ClassLoader.class.getDeclaredField("sys_paths");
        sysPaths.setAccessible(true);
        sysPaths.set(null, null);
    }
}
