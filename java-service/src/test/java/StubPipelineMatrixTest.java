import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import org.junit.Test;

public class StubPipelineMatrixTest {

    @Test
    public void allMinerFamiliesAndPreprocessingsAreAcceptedInPipelineContract() throws Exception {
        Path tmp = Files.createTempDirectory("stub-matrix-test");
        ArtifactStore store = new ArtifactStore(tmp.toString());
        StubPipelineEvaluator evaluator = new StubPipelineEvaluator(store);

        List<PipelineRequest.PreprocessingConfig> preprocessings = TestFixtures.allPreprocessings();
        List<PipelineRequest.MinerConfig> miners = TestFixtures.allMinerFamilies();
        List<String> metrics = TestFixtures.defaultMetrics();

        int evalCount = 0;
        for (PipelineRequest.PreprocessingConfig preprocessing : preprocessings) {
            for (PipelineRequest.MinerConfig miner : miners) {
                String experimentId = "matrix_" + preprocessing.key + "_" + miner.key;
                PipelineRequest request = TestFixtures.buildRequest(
                    experimentId,
                    "/tmp/log.xes",
                    preprocessing,
                    miner,
                    metrics
                );

                EvaluationResult result = evaluator.evaluate(request);
                evalCount += 1;

                assertEquals(experimentId, result.experiment_id);
                assertTrue(result.fingerprint.contains(preprocessing.key));
                assertTrue(result.fingerprint.contains(miner.key));
                TestFixtures.assertMetricsRange(result.metrics, metrics);

                ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
                assertEquals(1, bulk.artifacts.size());
                ArtifactBulkResponse.ArtifactEntry entry = bulk.artifacts.get(0);
                assertEquals(preprocessing.key, entry.pipeline.preprocessing.key);
                assertEquals(miner.key, entry.pipeline.miner.key);
                assertTrue(entry.pnml.contains("stub-net"));
            }
        }

        assertEquals(preprocessings.size() * miners.size(), evalCount);
    }
}
