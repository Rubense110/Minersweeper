import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;

import java.io.File;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;

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
            TestFixtures.assertMetricsRange(result.metrics, TestFixtures.defaultMetrics());

            ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
            assertEquals(1, bulk.artifacts.size());
            assertEquals(miner.key, bulk.artifacts.get(0).pipeline.miner.key);
            assertTrue(bulk.artifacts.get(0).pnml.contains("pnml"));
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
