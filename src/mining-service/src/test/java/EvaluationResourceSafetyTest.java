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
    private static class Memory implements EvaluationAdmission.MemoryProbe {
        volatile long used = 95;
        volatile boolean reclaimable = true;
        final java.util.concurrent.atomic.AtomicInteger collections = new java.util.concurrent.atomic.AtomicInteger();
        public long maximum() { return 100; }
        public long used() { return used; }
        public void collect() { collections.incrementAndGet(); if (reclaimable) used = 20; }
    }

    @Test public void idleGarbageIsReclaimedBeforeRejectingCapacity() throws Exception {
        Memory memory = new Memory();
        EvaluationAdmission admission = new EvaluationAdmission(1, 10, memory, 50);
        try (EvaluationAdmission.Permit permit = admission.acquire(new ExperimentExecutionRegistry(), "e", "r")) {
            assertEquals(1, admission.active());
            assertEquals(1, memory.collections.get());
        }
        assertEquals(0, admission.active());
        assertEquals(0, admission.waiting());
    }

    @Test public void persistentLivePressureStillRejectsAndReleasesItsSlot() throws Exception {
        Memory memory = new Memory(); memory.reclaimable = false;
        EvaluationAdmission admission = new EvaluationAdmission(1, 10, memory, 50);
        try { admission.acquire(new ExperimentExecutionRegistry(), "e", "r"); fail(); }
        catch (EvaluationAdmission.CapacityExceeded expected) {
            assertTrue(expected.getMessage().contains("idle reclamation"));
        }
        assertEquals(0, admission.active());
        assertEquals(0, admission.waiting());
        memory.used = 20;
        try (EvaluationAdmission.Permit permit = admission.acquire(new ExperimentExecutionRegistry(), "e", "next")) {
            assertEquals(1, admission.active());
        }
    }

    @Test public void pressureDoesNotTimeOutWhileAnotherEvaluationIsActive() throws Exception {
        Memory memory = new Memory(); memory.used = 20;
        EvaluationAdmission admission = new EvaluationAdmission(2, 10, memory, 50);
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        EvaluationAdmission.Permit first = admission.acquire(registry, "e", "first");
        memory.used = 95;
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> second = executor.submit(() -> {
                try (EvaluationAdmission.Permit permit = admission.acquire(registry, "e", "second")) { }
                catch (InterruptedException error) { throw new RuntimeException(error); }
            });
            long limit = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
            while (admission.waiting() == 0 && System.nanoTime() < limit) Thread.yield();
            assertEquals(1, admission.waiting());
            try { second.get(250, TimeUnit.MILLISECONDS); fail("busy pressure must wait beyond idle timeout"); }
            catch (TimeoutException expected) { }
            assertEquals(0, memory.collections.get());
            first.close();
            second.get(2, TimeUnit.SECONDS);
            assertEquals(1, memory.collections.get());
            assertEquals(0, admission.active());
        } finally { first.close(); executor.shutdownNow(); }
    }

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
