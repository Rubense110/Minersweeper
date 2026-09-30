package com.minersweeper.javaservice.evaluation;

import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Global slots remain occupied until an actual Java evaluation leaves its scope. */
public final class EvaluationAdmission {
    private final Semaphore slots;
    private final int maximum;
    private final long reserveBytes;
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger waiting = new AtomicInteger();

    public EvaluationAdmission() {
        this(positiveEnv("PROM_MAX_CONCURRENT_EVALUATIONS", Math.min(4, Runtime.getRuntime().availableProcessors())),
            positiveEnv("PROM_EVALUATION_RESERVE_MB", 512) * 1024L * 1024L);
    }
    public EvaluationAdmission(int maximum, long reserveBytes) {
        if (maximum < 1 || reserveBytes < 0) throw new IllegalArgumentException("Invalid admission limits");
        this.maximum = maximum; this.reserveBytes = reserveBytes; slots = new Semaphore(maximum, true);
    }
    public Permit acquire(ExperimentExecutionRegistry registry, String experiment, String request) throws InterruptedException {
        if (waiting.incrementAndGet() > maximum * 2) {
            waiting.decrementAndGet(); throw new CapacityExceeded("Evaluation queue is full");
        }
        boolean acquired = false;
        long pressureSince = 0L;
        try {
            while (!acquired) {
                registry.throwIfCancellationRequested(experiment, request);
                ExecutionChecks.check();
                Runtime runtime = Runtime.getRuntime();
                long used = runtime.totalMemory() - runtime.freeMemory();
                long headroom = Math.min(reserveBytes, runtime.maxMemory() / 8L);
                // This is a conservative admission signal, not an exact estimate
                // of the plugin's future peak. The hard slot limit always applies.
                if (runtime.maxMemory() - used >= headroom * 2L) {
                    pressureSince = 0L;
                    acquired = slots.tryAcquire(100L, TimeUnit.MILLISECONDS);
                } else {
                    if (pressureSince == 0L) pressureSince = System.nanoTime();
                    if (System.nanoTime() - pressureSince > TimeUnit.SECONDS.toNanos(5L)) {
                        throw new CapacityExceeded("Insufficient heap headroom for another evaluation");
                    }
                    TimeUnit.MILLISECONDS.sleep(100L);
                }
            }
            registry.throwIfCancellationRequested(experiment, request);
            active.incrementAndGet();
            return new Permit();
        } catch (RuntimeException | InterruptedException failure) {
            if (acquired) slots.release();
            throw failure;
        } finally { waiting.decrementAndGet(); }
    }
    public int active() { return active.get(); }
    public int waiting() { return waiting.get(); }
    public static int positiveEnv(String key, int fallback) {
        try { int value = Integer.parseInt(System.getenv(key)); return value > 0 ? value : fallback; }
        catch (RuntimeException invalid) { return fallback; }
    }
    public final class Permit implements AutoCloseable {
        private boolean closed;
        @Override public void close() {
            if (!closed) { closed = true; active.decrementAndGet(); slots.release(); }
        }
    }
    public static final class CapacityExceeded extends RuntimeException {
        CapacityExceeded(String message) { super(message); }
    }
}
