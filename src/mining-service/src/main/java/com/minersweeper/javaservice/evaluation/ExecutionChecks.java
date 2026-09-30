package com.minersweeper.javaservice.evaluation;

import java.util.concurrent.CancellationException;

/** Cooperative checks for our loops; never clears interruption. */
public final class ExecutionChecks {
    private static final ThreadLocal<Long> DEADLINE = new ThreadLocal<Long>();
    private ExecutionChecks() {}
    public static void check() {
        if (Thread.currentThread().isInterrupted()) throw new CancellationException("evaluation interrupted");
        Long deadline = DEADLINE.get();
        if (deadline != null && System.nanoTime() - deadline.longValue() >= 0L) throw new DeadlineExceeded();
    }
    public static Deadline within(long nanos) { return new Deadline(nanos); }
    public static final class DeadlineExceeded extends RuntimeException {}
    public static final class Deadline implements AutoCloseable {
        private final Long previous = DEADLINE.get();
        private Deadline(long nanos) {
            long deadline = System.nanoTime() + nanos;
            DEADLINE.set(previous == null ? deadline : Math.min(previous.longValue(), deadline));
        }
        @Override public void close() {
            if (previous == null) DEADLINE.remove(); else DEADLINE.set(previous);
        }
    }
}
