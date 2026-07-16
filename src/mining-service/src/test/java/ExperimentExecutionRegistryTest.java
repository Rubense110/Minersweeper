import com.minersweeper.javaservice.evaluation.ExperimentCancelledException;
import com.minersweeper.javaservice.evaluation.ExperimentExecutionRegistry;
import org.junit.Test;

import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class ExperimentExecutionRegistryTest {

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
