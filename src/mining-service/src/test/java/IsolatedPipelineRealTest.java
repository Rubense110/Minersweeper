import com.minersweeper.javaservice.api.dto.*;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;
import com.minersweeper.javaservice.evaluation.isolation.*;
import java.nio.file.*;
import java.util.*;
import org.junit.Test;
import static org.junit.Assert.*;

public class IsolatedPipelineRealTest {
    @Test public void realInductivePipelinePreservesSemanticDigestMetricsAndNativeArtifacts() throws Exception {
        Path root=Files.createTempDirectory("isolated-real");Path log=TestFixtures.createTinyLog(root,"tiny.xes");
        ArtifactStore directStore=new ArtifactStore(root.resolve("direct").toString());
        PipelineRequest direct=TestFixtures.buildRequest("direct",log.toString(),TestFixtures.variantFilter(),TestFixtures.inductiveImf(),TestFixtures.defaultMetrics());
        direct.conformance_mode="replay-token";
        EvaluationResult baseline=new PromPipelineEvaluator(directStore,root).evaluate(direct);
        ArtifactStore stable=new ArtifactStore(root.resolve("stable").toString());
        WorkerPoolConfig config=new WorkerPoolConfig(1,"256m",30000,100,15000,1000,3000,IsolatedWorkerMain.class.getName());
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(stable,root,root.resolve("workers"),config)) {
            PipelineRequest isolated=TestFixtures.buildRequest("isolated",log.toString(),TestFixtures.variantFilter(),TestFixtures.inductiveImf(),TestFixtures.defaultMetrics());
            isolated.conformance_mode="replay-token";
            EvaluationResult result=pool.evaluate(isolated);
            assertEquals(baseline.model_semantic_sha256,result.model_semantic_sha256);
            assertEquals(baseline.metrics,result.metrics);assertEquals(baseline.is_feasible,result.is_feasible);
            ArtifactBulkResponse.ArtifactEntry a=stable.readBulk("isolated",Arrays.asList(result.evaluation_id),true).artifacts.get(0);
            ArtifactBulkResponse.ArtifactEntry b=directStore.readBulk("direct",Arrays.asList(baseline.evaluation_id),true).artifacts.get(0);
            // Separate discoveries contain ProM-local UUIDs and can assign different PNML IDs.
            // Structural identity is asserted above through the canonical semantic digest.
            assertTrue(a.pnml.contains("<pnml"));
            assertEquals(b.initial_marking.size(),a.initial_marking.size());
            assertEquals(b.final_markings.size(),a.final_markings.size());
            assertEquals(b.transitions.size(),a.transitions.size());
            for (ArtifactBulkResponse.MarkingEntry mark:a.initial_marking) {
                assertTrue(a.pnml.contains("id=\""+mark.place_id+"\""));
                assertTrue(mark.tokens>0);
            }
            for (ArtifactBulkResponse.TransitionEntry transition:a.transitions)
                assertTrue(a.pnml.contains("id=\""+transition.id+"\""));
        }
    }
}
