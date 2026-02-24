package com.minersweeper.javaservice.app.logging;

import java.io.PrintStream;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

public final class TimingTrace {
    private static final boolean ENABLED = Boolean.parseBoolean(env("PROM_TIMING_ENABLED", "false"));
    private static final long SLOW_THRESHOLD_MS = parseLong(env("PROM_TIMING_SLOW_MS", "0"), 0L);
    private static final AtomicLong TRACE_SEQUENCE = new AtomicLong(0L);

    private final String traceId;
    private final boolean enabled;
    private final Map<String, String> fields = new LinkedHashMap<String, String>();
    private final Map<String, Long> durationsMs = new LinkedHashMap<String, Long>();

    private TimingTrace(boolean enabled, String traceId) {
        this.enabled = enabled;
        this.traceId = traceId;
    }

    public static TimingTrace start() {
        long sequence = TRACE_SEQUENCE.incrementAndGet();
        String generatedTraceId = Long.toHexString(System.currentTimeMillis()) + "-" + sequence;
        return new TimingTrace(ENABLED, generatedTraceId);
    }

    public static long nowNs() {
        return System.nanoTime();
    }

    public static long elapsedMs(long startedAtNs) {
        return (System.nanoTime() - startedAtNs) / 1_000_000L;
    }

    public boolean enabled() {
        return enabled;
    }

    public String traceId() {
        return traceId;
    }

    public void markFromStart(String phaseKey, long startedAtNs) {
        if (!enabled) {
            return;
        }
        markDurationMs(phaseKey, elapsedMs(startedAtNs));
    }

    public void markDurationMs(String phaseKey, long durationMs) {
        if (!enabled) {
            return;
        }
        durationsMs.put(phaseKey, Long.valueOf(durationMs));
    }

    public void putField(String key, String value) {
        if (!enabled) {
            return;
        }
        if (key == null || key.trim().isEmpty()) {
            return;
        }
        fields.put(key, value == null ? "" : value);
    }

    public Map<String, String> fields() {
        return Collections.unmodifiableMap(fields);
    }

    public void logSummary(
        long totalMs,
        boolean failed,
        String failureType,
        String experimentId,
        String minerKey,
        String minerVariant,
        String preprocessingKey,
        String requestedMetrics
    ) {
        if (!enabled) {
            return;
        }
        if (!failed && SLOW_THRESHOLD_MS > 0L && totalMs < SLOW_THRESHOLD_MS) {
            return;
        }

        StringBuilder line = new StringBuilder(512);
        line.append("prom_service timing");
        appendField(line, "trace_id", traceId);
        appendField(line, "event", "evaluation_summary");
        appendField(line, "status", failed ? "failed" : "ok");
        appendField(line, "total_ms", Long.toString(totalMs));
        appendField(line, "experiment_id", experimentId);
        appendField(line, "miner_key", minerKey);
        appendField(line, "miner_variant", minerVariant);
        appendField(line, "preprocessing_key", preprocessingKey);
        appendField(line, "metrics", requestedMetrics);
        if (failed) {
            appendField(line, "error_type", failureType);
        }
        for (Map.Entry<String, String> entry : fields.entrySet()) {
            appendField(line, entry.getKey(), entry.getValue());
        }
        for (Map.Entry<String, Long> entry : durationsMs.entrySet()) {
            appendField(line, entry.getKey(), String.valueOf(entry.getValue()));
        }
        PrintStream err = UnknownExtensionLogFilter.originalErr();
        err.println(line.toString());
        err.flush();
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value.trim();
    }

    private static long parseLong(String value, long fallback) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static void appendField(StringBuilder line, String key, String value) {
        line.append(' ').append(key).append('=').append(quoteIfNeeded(value));
    }

    private static String quoteIfNeeded(String value) {
        String safe = value == null ? "" : value;
        boolean needsQuotes = false;
        for (int i = 0; i < safe.length(); i++) {
            char c = safe.charAt(i);
            if (Character.isWhitespace(c) || c == '=' || c == '"' || c == '\\') {
                needsQuotes = true;
                break;
            }
        }
        if (!needsQuotes) {
            return safe;
        }
        String escaped = safe.replace("\\", "\\\\").replace("\"", "\\\"");
        return "\"" + escaped + "\"";
    }
}
