package com.minersweeper.javaservice.evaluation.conformance;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class TokenReplayResult {
    private final long missing;
    private final long consumed;
    private final long remaining;
    private final long produced;
    private final long traceCount;
    private final long fitTraceCount;
    private final Map<Transition, Integer> transitionActivations;

    public TokenReplayResult(
        long missing,
        long consumed,
        long remaining,
        long produced,
        long traceCount,
        long fitTraceCount,
        Map<Transition, Integer> transitionActivations
    ) {
        this.missing = missing;
        this.consumed = consumed;
        this.remaining = remaining;
        this.produced = produced;
        this.traceCount = traceCount;
        this.fitTraceCount = fitTraceCount;
        this.transitionActivations = Collections.unmodifiableMap(
            new LinkedHashMap<Transition, Integer>(transitionActivations)
        );
    }

    public long missing() {
        return missing;
    }

    public long consumed() {
        return consumed;
    }

    public long remaining() {
        return remaining;
    }

    public long produced() {
        return produced;
    }

    public long traceCount() {
        return traceCount;
    }

    public long fitTraceCount() {
        return fitTraceCount;
    }

    public Map<Transition, Integer> transitionActivations() {
        return transitionActivations;
    }

    public double fitness() {
        if (consumed <= 0 || produced <= 0) {
            return 1.0;
        }
        double consumedFitness = 1.0 - ((double) missing / (double) consumed);
        double producedFitness = 1.0 - ((double) remaining / (double) produced);
        return 0.5 * consumedFitness + 0.5 * producedFitness;
    }
}
