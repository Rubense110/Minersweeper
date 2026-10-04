package com.minersweeper.javaservice.evaluation;

import java.util.concurrent.CancellationException;

/** Cooperative checks for our loops; never clears interruption. */
public final class ExecutionChecks {
    private static final ThreadLocal<Long> DEADLINE = new ThreadLocal<Long>();
    private static final ThreadLocal<Work> WORK = new ThreadLocal<Work>();
    private ExecutionChecks() {}
    public static void check() {
        if (Thread.currentThread().isInterrupted()) throw new CancellationException("evaluation interrupted");
        Work work = WORK.get();
        if (work != null && ++work.used > work.limit) throw new WorkLimitExceeded();
        Long deadline = DEADLINE.get();
        if (deadline != null && System.nanoTime() - deadline.longValue() >= 0L) throw new DeadlineExceeded();
    }
    public static Deadline within(long nanos) { return new Deadline(nanos); }
    public static final class DeadlineExceeded extends ReproducibilityException {
        public DeadlineExceeded() { super("REPRODUCIBILITY_TIME_LIMIT"); }
    }
    public static final class WorkLimitExceeded extends RuntimeException {}
    public static Work withinWork(long limit) { return new Work(limit); }
    public static final class Work implements AutoCloseable {
        private final Work previous = WORK.get();
        private final long limit;
        private long used;
        private Work(long limit) { this.limit = limit; WORK.set(this); }
        @Override public void close() { if (previous == null) WORK.remove(); else WORK.set(previous); }
    }
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
