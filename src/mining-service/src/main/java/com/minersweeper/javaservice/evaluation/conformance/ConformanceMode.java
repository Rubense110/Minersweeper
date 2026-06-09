package com.minersweeper.javaservice.evaluation.conformance;

public enum ConformanceMode {
    ALIGNMENT("alignment"),
    REPLAY("replay"),
    REPLAY_TOKEN("replay-token");

    private final String key;

    ConformanceMode(String key) {
        this.key = key;
    }

    public String key() {
        return key;
    }

    public boolean isAlignment() {
        return this == ALIGNMENT;
    }

    public boolean isReplay() {
        return this == REPLAY;
    }

    public boolean isReplayToken() {
        return this == REPLAY_TOKEN;
    }

    public static ConformanceMode resolve(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return ALIGNMENT;
        }
        String normalized = raw.trim().toLowerCase();
        for (ConformanceMode mode : values()) {
            if (mode.key.equals(normalized)) {
                return mode;
            }
        }
        throw new IllegalArgumentException("unsupported conformance_mode: " + raw);
    }
}
