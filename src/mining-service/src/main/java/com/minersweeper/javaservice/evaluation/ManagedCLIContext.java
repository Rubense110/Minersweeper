package com.minersweeper.javaservice.evaluation;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;

/** One root context per evaluation, with owned executor lifetime. */
public final class ManagedCLIContext extends CLIContext implements AutoCloseable {
    public CLIPluginContext plugin() { return getMainPluginContext(); }
    @Override public void close() {
        ExecutorService executor = (ExecutorService) plugin().getExecutor();
        executor.shutdownNow();
        boolean interrupted = Thread.interrupted();
        try {
            // Do not publish termination or release admission while known child
            // tasks are still alive. A non-cooperative task keeps the slot held.
            while (!executor.isTerminated()) {
                try { executor.awaitTermination(100L, TimeUnit.MILLISECONDS); }
                catch (InterruptedException again) { interrupted = true; }
            }
        } finally { if (interrupted) Thread.currentThread().interrupt(); }
    }
}
