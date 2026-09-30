import static org.junit.Assert.*;
import com.minersweeper.javaservice.evaluation.*;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.Test;

public class EvaluationResourceSafetyTest {
    @Test public void cancellationDoesNotConfirmUntilLeaseClosesAndRejectsLateRequests() throws Exception {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        ExperimentExecutionRegistry.EvaluationLease lease = registry.registerEvaluation("experiment", "request");
        assertEquals(Boolean.FALSE, registry.terminationConfirmed("experiment", "request"));
        registry.requestCancelEvaluation("experiment", "request");
        try {
            assertEquals(Boolean.FALSE, registry.terminationConfirmed("experiment", "request"));
            lease.close();
            assertEquals(Boolean.TRUE, registry.terminationConfirmed("experiment", "request"));
            try { registry.registerEvaluation("experiment", "request"); fail(); }
            catch (ExperimentCancelledException expected) { }
        } finally { Thread.interrupted(); }
        registry.cleanupExperiment("experiment");
        try { registry.registerEvaluation("experiment", "another"); fail(); }
        catch (ExperimentCancelledException expected) { }
        assertNull(registry.terminationConfirmed("unknown", "request"));
    }

    @Test public void waitingEvaluationCannotTakeOccupiedSlotAndCancelsPromptly() throws Exception {
        EvaluationAdmission admission = new EvaluationAdmission(1, 0L);
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        EvaluationAdmission.Permit first = admission.acquire(registry, "experiment", "first");
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> waiting = executor.submit(() -> {
                try (EvaluationAdmission.Permit ignored = admission.acquire(registry, "experiment", "waiting")) {
                    fail("occupied slot was admitted");
                } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            });
            long limit = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (admission.waiting() == 0 && System.nanoTime() < limit) Thread.yield();
            assertEquals(1, admission.active());
            assertEquals(1, admission.waiting());
            registry.requestCancelEvaluation("experiment", "waiting");
            try { waiting.get(2, TimeUnit.SECONDS); fail(); }
            catch (ExecutionException expected) { assertTrue(expected.getCause() instanceof ExperimentCancelledException); }
            assertEquals(0, admission.waiting());
            assertEquals(1, admission.active());
        } finally { first.close(); executor.shutdownNow(); }
        assertEquals(0, admission.active());
        try (EvaluationAdmission.Permit next = admission.acquire(registry, "experiment", "next")) {
            assertEquals(1, admission.active());
        }
    }

    @Test public void managedContextWaitsForOwnedTaskAndPreservesInterrupt() throws Exception {
        ManagedCLIContext context = new ManagedCLIContext();
        CountDownLatch started = new CountDownLatch(1);
        Future<?> task = ((ExecutorService) context.plugin().getExecutor()).submit(() -> {
            started.countDown();
            try { new CountDownLatch(1).await(); }
            catch (InterruptedException expected) { Thread.currentThread().interrupt(); }
        });
        assertTrue(started.await(2, TimeUnit.SECONDS));
        Thread.currentThread().interrupt();
        try {
            context.close();
            assertTrue(task.isDone());
            assertTrue(Thread.currentThread().isInterrupted());
        } finally { Thread.interrupted(); }
    }

    @Test public void cancelledArtifactWritePublishesNoFiles() throws Exception {
        Path root = Files.createTempDirectory("artifact-cancelled");
        PipelineRequest request = new PipelineRequest(); request.experiment_id = "cancelled";
        Thread.currentThread().interrupt();
        try {
            new ArtifactStore(root.toString()).store(request, Collections.<String, Double>emptyMap(), "<pnml/>", "fp");
            fail();
        } catch (CancellationException expected) {
            try (java.util.stream.Stream<Path> files = Files.list(root.resolve("cancelled"))) {
                assertEquals(0L, files.count());
            }
        } finally { Thread.interrupted(); Files.deleteIfExists(root.resolve("cancelled")); Files.deleteIfExists(root); }
    }

    @Test public void deadlineIsScopedAndNonFiniteMetricsNeverBecomeValidZeros() {
        try (ExecutionChecks.Deadline ignored = ExecutionChecks.within(-1L)) {
            try { ExecutionChecks.check(); fail(); }
            catch (ExecutionChecks.DeadlineExceeded expected) { }
        }
        ExecutionChecks.check();
        for (double value : new double[]{Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY}) {
            try { MetricUtils.clamp01(value); fail(); } catch (IllegalStateException expected) { }
            try { MetricUtils.toDouble(value, 0.0); fail(); } catch (IllegalStateException expected) { }
        }
    }
}
