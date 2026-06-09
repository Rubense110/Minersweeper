package com.minersweeper.javaservice.evaluation.conformance;

public class TokenReplayPrecisionResult {
    private final long prefixCount;
    private final long replayedPrefixCount;
    private final long activatedTransitions;
    private final long escapingEdges;

    public TokenReplayPrecisionResult(
        long prefixCount,
        long replayedPrefixCount,
        long activatedTransitions,
        long escapingEdges
    ) {
        this.prefixCount = prefixCount;
        this.replayedPrefixCount = replayedPrefixCount;
        this.activatedTransitions = activatedTransitions;
        this.escapingEdges = escapingEdges;
    }

    public long prefixCount() {
        return prefixCount;
    }

    public long replayedPrefixCount() {
        return replayedPrefixCount;
    }

    public long activatedTransitions() {
        return activatedTransitions;
    }

    public long escapingEdges() {
        return escapingEdges;
    }

    public double precision() {
        if (activatedTransitions <= 0L) {
            return 1.0;
        }
        return 1.0 - ((double) escapingEdges / (double) activatedTransitions);
    }
}
