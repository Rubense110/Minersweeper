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
    private final Map<String, Set<Thread>> threadsByEvaluation = new LinkedHashMap<String, Set<Thread>>();
    private final Set<String> cancelledEvaluations = new LinkedHashSet<String>();

    public EvaluationLease registerEvaluation(String experimentId) {
        return registerEvaluation(experimentId, null);
    }

    public EvaluationLease registerEvaluation(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        Thread thread = Thread.currentThread();

        synchronized (this) {
            Set<Thread> experimentThreads = threadsByExperiment.get(normalizedExperiment);
            if (experimentThreads == null) {
                experimentThreads = new LinkedHashSet<Thread>();
                threadsByExperiment.put(normalizedExperiment, experimentThreads);
            }
            experimentThreads.add(thread);

            if (normalizedRequest != null) {
                Set<Thread> evaluationThreads = threadsByEvaluation.get(evaluationKey(normalizedExperiment, normalizedRequest));
                if (evaluationThreads == null) {
                    evaluationThreads = new LinkedHashSet<Thread>();
                    threadsByEvaluation.put(evaluationKey(normalizedExperiment, normalizedRequest), evaluationThreads);
                }
                evaluationThreads.add(thread);
            }

            if (!stateByExperiment.containsKey(normalizedExperiment)) {
                stateByExperiment.put(normalizedExperiment, ExperimentExecutionState.ACTIVE);
            }
        }

        return new EvaluationLease(this, normalizedExperiment, normalizedRequest, thread);
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

        interruptAll(threadsToInterrupt);
    }

    public void requestCancelEvaluation(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeRequestId(requestId);
        String key = evaluationKey(normalizedExperiment, normalizedRequest);
        Set<Thread> threadsToInterrupt;

        synchronized (this) {
            cancelledEvaluations.add(key);
            Set<Thread> threads = threadsByEvaluation.get(key);
            threadsToInterrupt = threads == null
                ? Collections.<Thread>emptySet()
                : new LinkedHashSet<Thread>(threads);
        }

        interruptAll(threadsToInterrupt);
    }

    public synchronized boolean isCancellationRequested(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        return stateByExperiment.get(normalized) == ExperimentExecutionState.CANCEL_REQUESTED;
    }

    public synchronized boolean isCancellationRequested(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        if (stateByExperiment.get(normalizedExperiment) == ExperimentExecutionState.CANCEL_REQUESTED) {
            return true;
        }
        return normalizedRequest != null && cancelledEvaluations.contains(evaluationKey(normalizedExperiment, normalizedRequest));
    }

    public void throwIfCancellationRequested(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        if (isCancellationRequested(normalized)) {
            throw new ExperimentCancelledException("experiment '" + normalized + "' cancelled");
        }
    }

    public synchronized void throwIfCancellationRequested(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        if (stateByExperiment.get(normalizedExperiment) == ExperimentExecutionState.CANCEL_REQUESTED) {
            throw new ExperimentCancelledException("experiment '" + normalizedExperiment + "' cancelled");
        }
        if (normalizedRequest != null && cancelledEvaluations.contains(evaluationKey(normalizedExperiment, normalizedRequest))) {
            throw new ExperimentCancelledException(
                "evaluation '" + normalizedRequest + "' cancelled for experiment '" + normalizedExperiment + "'"
            );
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
            removeExperimentEvaluations(normalized);
        }
    }

    private synchronized void unregister(String experimentId, String requestId, Thread thread) {
        Set<Thread> experimentThreads = threadsByExperiment.get(experimentId);
        if (experimentThreads != null) {
            experimentThreads.remove(thread);
            if (experimentThreads.isEmpty()) {
                threadsByExperiment.remove(experimentId);
            }
        }

        if (requestId != null) {
            String key = evaluationKey(experimentId, requestId);
            Set<Thread> evaluationThreads = threadsByEvaluation.get(key);
            if (evaluationThreads != null) {
                evaluationThreads.remove(thread);
                if (evaluationThreads.isEmpty()) {
                    threadsByEvaluation.remove(key);
                    cancelledEvaluations.remove(key);
                }
            }
        }
        notifyAll();
    }

    private boolean hasActiveEvaluations(String experimentId) {
        Set<Thread> threads = threadsByExperiment.get(experimentId);
        return threads != null && !threads.isEmpty();
    }

    private void removeExperimentEvaluations(String experimentId) {
        String prefix = experimentId + "\u0000";
        Set<String> keysToRemove = new LinkedHashSet<String>();
        for (String key : threadsByEvaluation.keySet()) {
            if (key.startsWith(prefix)) {
                keysToRemove.add(key);
            }
        }
        for (String key : keysToRemove) {
            threadsByEvaluation.remove(key);
            cancelledEvaluations.remove(key);
        }
    }

    private static void interruptAll(Set<Thread> threads) {
        for (Thread thread : threads) {
            thread.interrupt();
        }
    }

    private static String normalizeExperimentId(String experimentId) {
        String normalized = experimentId == null ? "" : experimentId.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("experiment_id is required");
        }
        return normalized;
    }

    private static String normalizeRequestId(String requestId) {
        String normalized = normalizeOptionalRequestId(requestId);
        if (normalized == null) {
            throw new IllegalArgumentException("request_id is required");
        }
        return normalized;
    }

    private static String normalizeOptionalRequestId(String requestId) {
        String normalized = requestId == null ? "" : requestId.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static String evaluationKey(String experimentId, String requestId) {
        return experimentId + "\u0000" + requestId;
    }

    private enum ExperimentExecutionState {
        ACTIVE,
        CANCEL_REQUESTED
    }

    public static final class EvaluationLease implements AutoCloseable {
        private final ExperimentExecutionRegistry registry;
        private final String experimentId;
        private final String requestId;
        private final Thread thread;

        private EvaluationLease(ExperimentExecutionRegistry registry, String experimentId, String requestId, Thread thread) {
            this.registry = registry;
            this.experimentId = experimentId;
            this.requestId = requestId;
            this.thread = thread;
        }

        @Override
        public void close() {
            registry.unregister(experimentId, requestId, thread);
        }
    }
}
