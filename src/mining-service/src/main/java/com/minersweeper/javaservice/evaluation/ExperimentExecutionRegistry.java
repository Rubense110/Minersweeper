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
    private final Set<String> closedExperiments = new LinkedHashSet<String>();
    private final Set<String> completedEvaluations = new LinkedHashSet<String>();

    public EvaluationLease registerEvaluation(String experimentId) {
        return registerEvaluation(experimentId, null);
    }

    public EvaluationLease registerEvaluation(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        Thread thread = Thread.currentThread();

        synchronized (this) {
            if (closedExperiments.contains(normalizedExperiment))
                throw new ExperimentCancelledException("experiment '" + normalizedExperiment + "' has been cleaned up");
            throwIfCancellationRequested(normalizedExperiment, normalizedRequest);
            if (normalizedRequest != null) {
                String key = evaluationKey(normalizedExperiment, normalizedRequest);
                if (completedEvaluations.contains(key) || threadsByEvaluation.containsKey(key))
                    throw new IllegalArgumentException("request_id already used: " + normalizedRequest);
            }
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

    public boolean isCancellationRequested(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        return isCancellationRequestedForKey(normalizedExperiment,
            normalizedRequest == null ? null : evaluationKey(normalizedExperiment, normalizedRequest));
    }

    /** Resolve identifiers once for callbacks invoked inside miner loops. */
    public CancellationCheck cancellationCheck(String experimentId, String requestId) {
        String normalizedExperiment = normalizeExperimentId(experimentId);
        String normalizedRequest = normalizeOptionalRequestId(requestId);
        return new CancellationCheck(this, normalizedExperiment,
            normalizedRequest == null ? null : evaluationKey(normalizedExperiment, normalizedRequest));
    }

    private synchronized boolean isCancellationRequestedForKey(String experimentId, String key) {
        if (stateByExperiment.get(experimentId) == ExperimentExecutionState.CANCEL_REQUESTED) {
            return true;
        }
        return key != null && cancelledEvaluations.contains(key);
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

    public synchronized Boolean terminationConfirmed(String experimentId, String requestId) {
        String experiment = normalizeExperimentId(experimentId);
        String key = evaluationKey(experiment, normalizeRequestId(requestId));
        Set<Thread> threads = threadsByEvaluation.get(key);
        if (threads != null && !threads.isEmpty()) return Boolean.FALSE;
        if (completedEvaluations.contains(key) || cancelledEvaluations.contains(key)
            || closedExperiments.contains(experiment)) return Boolean.TRUE;
        return null; // Unknown is not proof that a request cannot arrive later.
    }

    public void cleanupExperiment(String experimentId) throws InterruptedException {
        String normalized = normalizeExperimentId(experimentId);
        synchronized (this) {
            closedExperiments.add(normalized); // Reject late arrivals before waiting.
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
                    completedEvaluations.add(key);
                    while (completedEvaluations.size() > 4096) completedEvaluations.remove(completedEvaluations.iterator().next());
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
        for (String key : keysToRemove) threadsByEvaluation.remove(key);
        cancelledEvaluations.removeIf(key -> key.startsWith(prefix));
        completedEvaluations.removeIf(key -> key.startsWith(prefix));
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

    public static final class CancellationCheck {
        private final ExperimentExecutionRegistry registry;
        private final String experimentId;
        private final String evaluationKey;

        private CancellationCheck(ExperimentExecutionRegistry registry, String experimentId, String evaluationKey) {
            this.registry = registry;
            this.experimentId = experimentId;
            this.evaluationKey = evaluationKey;
        }

        public boolean isCancellationRequested() {
            // Read the current state on every poll; only the identifiers are cached.
            return registry.isCancellationRequestedForKey(experimentId, evaluationKey);
        }
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
