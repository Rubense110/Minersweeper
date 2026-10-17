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
    private final Object reclamationLock = new Object();
    private final MemoryProbe memory;
    private final long pressureTimeoutNanos;

    public interface MemoryProbe {
        long maximum();
        long used();
        void collect();
    }

    public EvaluationAdmission() {
        this(positiveEnv("PROM_MAX_CONCURRENT_EVALUATIONS", Math.min(4, Runtime.getRuntime().availableProcessors())),
            positiveEnv("PROM_EVALUATION_RESERVE_MB", 512) * 1024L * 1024L);
    }
    public EvaluationAdmission(int maximum, long reserveBytes) {
        this(maximum, reserveBytes, new MemoryProbe() {
            public long maximum() { return Runtime.getRuntime().maxMemory(); }
            public long used() {
                Runtime runtime = Runtime.getRuntime();
                return runtime.totalMemory() - runtime.freeMemory();
            }
            public void collect() { System.gc(); }
        }, 5000L);
    }
    public EvaluationAdmission(int maximum, long reserveBytes, MemoryProbe memory, long pressureTimeoutMillis) {
        if (maximum < 1 || reserveBytes < 0) throw new IllegalArgumentException("Invalid admission limits");
        if (memory == null || pressureTimeoutMillis < 1) throw new IllegalArgumentException("Invalid memory probe or timeout");
        this.maximum = maximum; this.reserveBytes = reserveBytes; slots = new Semaphore(maximum, true);
        this.memory = memory;
        this.pressureTimeoutNanos = TimeUnit.MILLISECONDS.toNanos(pressureTimeoutMillis);
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
                acquired = slots.tryAcquire(100L, TimeUnit.MILLISECONDS);
            }
            boolean reclaimed = false;
            while (!hasHeadroom()) {
                registry.throwIfCancellationRequested(experiment, request);
                ExecutionChecks.check();
                // A busy evaluation may release its working set on completion.
                // Waiting for it is not evidence of exhausted idle capacity.
                if (active.get() > 0) {
                    pressureSince = 0L;
                    reclaimed = false;
                } else {
                    // With no work admitted, allocation-driven GC may never run.
                    // Reclaim once before measuring persistent idle pressure.
                    if (!reclaimed) {
                        synchronized (reclamationLock) {
                            if (active.get() == 0 && !hasHeadroom()) memory.collect();
                        }
                        reclaimed = true;
                        registry.throwIfCancellationRequested(experiment, request);
                        ExecutionChecks.check();
                        if (hasHeadroom()) break;
                    }
                    if (pressureSince == 0L) pressureSince = System.nanoTime();
                    if (System.nanoTime() - pressureSince > pressureTimeoutNanos) {
                        throw new CapacityExceeded("Insufficient heap headroom after idle reclamation");
                    }
                }
                TimeUnit.MILLISECONDS.sleep(100L);
            }
            registry.throwIfCancellationRequested(experiment, request);
            active.incrementAndGet();
            return new Permit();
        } catch (RuntimeException | InterruptedException failure) {
            if (acquired) slots.release();
            throw failure;
        } finally { waiting.decrementAndGet(); }
    }
    private boolean hasHeadroom() {
        long headroom = Math.min(reserveBytes, memory.maximum() / 8L);
        return memory.maximum() - memory.used() >= headroom * 2L;
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
