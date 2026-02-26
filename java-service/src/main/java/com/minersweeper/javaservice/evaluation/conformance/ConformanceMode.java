package com.minersweeper.javaservice.evaluation.conformance;

public enum ConformanceMode {
    ALIGNMENT("alignment"),
    REPLAY("replay");

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
