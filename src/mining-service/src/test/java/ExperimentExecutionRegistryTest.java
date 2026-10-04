import com.minersweeper.javaservice.evaluation.ExperimentCancelledException;
import com.minersweeper.javaservice.evaluation.ExperimentExecutionRegistry;
import org.junit.Test;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class ExperimentExecutionRegistryTest {

    @Test
    public void cachedCancellationCheckObservesIndividualAndExperimentCancellation() throws Exception {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        ExperimentExecutionRegistry.CancellationCheck first = registry.cancellationCheck(" run ", " first ");
        ExperimentExecutionRegistry.CancellationCheck second = registry.cancellationCheck("run", "second");
        ExperimentExecutionRegistry.CancellationCheck other = registry.cancellationCheck("other", "first");
        ExperimentExecutionRegistry.CancellationCheck experimentOnly = registry.cancellationCheck("run", " ");

        assertFalse(first.isCancellationRequested());
        registry.requestCancelEvaluation("run", "first");
        assertTrue(first.isCancellationRequested());
        assertFalse(second.isCancellationRequested());
        assertFalse(other.isCancellationRequested());
        assertFalse(experimentOnly.isCancellationRequested());

        registry.requestCancel("run");
        assertTrue(second.isCancellationRequested());
        assertTrue(experimentOnly.isCancellationRequested());
        assertFalse(other.isCancellationRequested());
        registry.cleanupExperiment("run");
        assertFalse(first.isCancellationRequested());
        assertFalse(second.isCancellationRequested());
    }

    @Test
    public void cachedCancellationCheckSeesCancellationRequestedBeforeItsCreation() {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        registry.requestCancelEvaluation("run", "first");
        assertTrue(registry.cancellationCheck(" run ", " first ").isCancellationRequested());
        assertFalse(registry.cancellationCheck("run", null).isCancellationRequested());
        registry.requestCancel("run");
        assertTrue(registry.cancellationCheck("run", null).isCancellationRequested());
    }

    @Test
    public void cachedCancellationCheckObservesCancellationFromAnotherThread() throws Exception {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        ExperimentExecutionRegistry.CancellationCheck check = registry.cancellationCheck("run", "request");
        CountDownLatch started = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<Throwable>();
        Thread polling = new Thread(() -> {
            try {
                assertFalse(check.isCancellationRequested());
                started.countDown();
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
                while (!check.isCancellationRequested() && System.nanoTime() < deadline) Thread.yield();
                assertTrue(check.isCancellationRequested());
            } catch (Throwable error) {
                failure.set(error);
            }
        });
        polling.start();
        try {
            assertTrue(started.await(2, TimeUnit.SECONDS));
            // The polling thread is deliberately not registered: observe the state
            // through the callback rather than through Thread.interrupt().
            registry.requestCancelEvaluation("run", "request");
        } finally {
            polling.join(3000L);
        }
        assertFalse(polling.isAlive());
        if (failure.get() != null) throw new AssertionError(failure.get());
    }

    @Test
    public void requestCancelMarksExperimentAsCancelled() {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();

        registry.requestCancel("run_cancel");

        assertTrue(registry.isCancellationRequested("run_cancel"));
        try {
            registry.throwIfCancellationRequested("run_cancel");
            fail("Expected ExperimentCancelledException");
        } catch (ExperimentCancelledException expected) {
            // expected
        }
    }

    @Test
    public void cleanupExperimentClearsCancelledState() throws Exception {
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        registry.requestCancel("run_cleanup");

        registry.cleanupExperiment("run_cleanup");

        assertTrue(!registry.isCancellationRequested("run_cleanup"));
    }

    @Test
    public void cleanupExperimentWaitsForActiveEvaluations() throws Exception {
        final ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        final Object gate = new Object();
        final boolean[] releaseWorker = new boolean[] { false };
        final boolean[] cleanupFinished = new boolean[] { false };

        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                try (ExperimentExecutionRegistry.EvaluationLease ignored = registry.registerEvaluation("run_wait")) {
                    boolean interrupted = false;
                    synchronized (gate) {
                        while (!releaseWorker[0]) {
                            try {
                                gate.wait();
                            } catch (InterruptedException expected) {
                                interrupted = true;
                            }
                        }
                    }
                    if (interrupted) {
                        Thread.currentThread().interrupt();
                    }
                }
            }
        });
        worker.start();
        Thread.sleep(50L);

        registry.requestCancel("run_wait");

        Thread cleanupThread = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    registry.cleanupExperiment("run_wait");
                    cleanupFinished[0] = true;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        });
        cleanupThread.start();
        Thread.sleep(50L);

        assertTrue(registry.isCancellationRequested("run_wait"));
        assertTrue(!cleanupFinished[0]);

        synchronized (gate) {
            releaseWorker[0] = true;
            gate.notifyAll();
        }

        cleanupThread.join(1000L);
        worker.join(1000L);

        assertTrue(cleanupFinished[0]);
        assertTrue(!registry.isCancellationRequested("run_wait"));
    }

    @Test
    public void requestCancelInterruptsRegisteredThread() throws Exception {
        final ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        final boolean[] interrupted = new boolean[] { false };

        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                try (ExperimentExecutionRegistry.EvaluationLease ignored = registry.registerEvaluation("run_interrupt")) {
                    try {
                        while (!Thread.currentThread().isInterrupted()) {
                            Thread.sleep(10L);
                        }
                    } catch (InterruptedException expected) {
                        interrupted[0] = true;
                        Thread.currentThread().interrupt();
                    }
                }
            }
        });

        worker.start();
        Thread.sleep(50L);

        registry.requestCancel("run_interrupt");
        worker.join(1000L);

        assertTrue(interrupted[0]);
    }
    @Test
    public void requestCancelEvaluationInterruptsOnlyMatchingThread() throws Exception {
        final ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        final boolean[] firstInterrupted = new boolean[] { false };
        final boolean[] secondInterrupted = new boolean[] { false };

        Thread first = interruptibleEvaluationThread(registry, "run_eval", "req_1", firstInterrupted);
        Thread second = interruptibleEvaluationThread(registry, "run_eval", "req_2", secondInterrupted);
        first.start();
        second.start();
        Thread.sleep(50L);

        registry.requestCancelEvaluation("run_eval", "req_1");
        first.join(1000L);
        Thread.sleep(50L);

        assertTrue(firstInterrupted[0]);
        assertTrue(!secondInterrupted[0]);
        registry.requestCancel("run_eval");
        second.join(1000L);
    }

    private static Thread interruptibleEvaluationThread(
        final ExperimentExecutionRegistry registry,
        final String experimentId,
        final String requestId,
        final boolean[] interrupted
    ) {
        return new Thread(new Runnable() {
            @Override
            public void run() {
                try (ExperimentExecutionRegistry.EvaluationLease ignored = registry.registerEvaluation(experimentId, requestId)) {
                    try {
                        while (!Thread.currentThread().isInterrupted()) {
                            Thread.sleep(10L);
                        }
                    } catch (InterruptedException expected) {
                        interrupted[0] = true;
                        Thread.currentThread().interrupt();
                    }
                }
            }
        });
    }

}
