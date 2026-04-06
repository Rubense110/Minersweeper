package com.minersweeper.javaservice.evaluation;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

public final class ExperimentExecutionRegistry {
    private final Map<String, ExperimentExecutionState> stateByExperiment =
        new LinkedHashMap<String, ExperimentExecutionState>();
    private final Map<String, Set<Thread>> threadsByExperiment = new LinkedHashMap<String, Set<Thread>>();

    public EvaluationLease registerEvaluation(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        Thread thread = Thread.currentThread();

        synchronized (this) {
            Set<Thread> threads = threadsByExperiment.get(normalized);
            if (threads == null) {
                threads = new LinkedHashSet<Thread>();
                threadsByExperiment.put(normalized, threads);
            }
            threads.add(thread);
            if (!stateByExperiment.containsKey(normalized)) {
                stateByExperiment.put(normalized, ExperimentExecutionState.ACTIVE);
            }
        }

        return new EvaluationLease(this, normalized, thread);
    }

    public void requestCancel(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        Set<Thread> threadsToInterrupt;

        synchronized (this) {
            stateByExperiment.put(normalized, ExperimentExecutionState.CANCEL_REQUESTED);
            Set<Thread> threads = threadsByExperiment.get(normalized);
            threadsToInterrupt = threads == null
                ? Collections.<Thread>emptySet()
                : new LinkedHashSet<Thread>(threads);
        }

        for (Thread thread : threadsToInterrupt) {
            thread.interrupt();
        }
    }

    public synchronized boolean isCancellationRequested(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        return stateByExperiment.get(normalized) == ExperimentExecutionState.CANCEL_REQUESTED;
    }

    public void throwIfCancellationRequested(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        if (isCancellationRequested(normalized)) {
            throw new ExperimentCancelledException("experiment '" + normalized + "' cancelled");
        }
    }

    public void cleanupExperiment(String experimentId) throws InterruptedException {
        String normalized = normalizeExperimentId(experimentId);
        synchronized (this) {
            while (hasActiveEvaluations(normalized)) {
                wait();
            }
            stateByExperiment.remove(normalized);
            threadsByExperiment.remove(normalized);
        }
    }

    private synchronized void unregister(String experimentId, Thread thread) {
        Set<Thread> threads = threadsByExperiment.get(experimentId);
        if (threads == null) {
            return;
        }
        threads.remove(thread);
        if (threads.isEmpty()) {
            threadsByExperiment.remove(experimentId);
        }
        notifyAll();
    }

    private boolean hasActiveEvaluations(String experimentId) {
        Set<Thread> threads = threadsByExperiment.get(experimentId);
        return threads != null && !threads.isEmpty();
    }

    private static String normalizeExperimentId(String experimentId) {
        String normalized = experimentId == null ? "" : experimentId.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("experiment_id is required");
        }
        return normalized;
    }

    private enum ExperimentExecutionState {
        ACTIVE,
        CANCEL_REQUESTED
    }

    public static final class EvaluationLease implements AutoCloseable {
        private final ExperimentExecutionRegistry registry;
        private final String experimentId;
        private final Thread thread;

        private EvaluationLease(ExperimentExecutionRegistry registry, String experimentId, Thread thread) {
            this.registry = registry;
            this.experimentId = experimentId;
            this.thread = thread;
        }

        @Override
        public void close() {
            registry.unregister(experimentId, thread);
        }
    }
}
