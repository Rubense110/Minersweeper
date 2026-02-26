package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.conformance.metrics.ConformanceMetric;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Fitness;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Generalisation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Precision;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Simplicity;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public enum ConformanceMetricCatalog {
    FITNESS(new Fitness(), MetricScope.ANY),
    PRECISION(new Precision(), MetricScope.ANY),
    GENERALISATION(new Generalisation(), MetricScope.ALIGNMENT_ONLY),
    SIMPLICITY(new Simplicity(), MetricScope.ANY);

    private static final Map<String, ConformanceMetric> METRICS_BY_KEY = new LinkedHashMap<String, ConformanceMetric>();
    private static final Map<String, MetricScope> SCOPE_BY_KEY = new LinkedHashMap<String, MetricScope>();
    private static final Map<String, String> ALIASES_TO_KEY = new LinkedHashMap<String, String>();

    static {
        for (ConformanceMetricCatalog entry : values()) {
            METRICS_BY_KEY.put(entry.metric.key(), entry.metric);
            SCOPE_BY_KEY.put(entry.metric.key(), entry.scope);
        }
        registerAlias(Fitness.KEY, Fitness.KEY);
        registerAlias(Precision.KEY, Precision.KEY);
        registerAlias("precision_alignment", Precision.KEY);
        registerAlias(Simplicity.KEY, Simplicity.KEY);
        registerAlias("simplicity_structural", Simplicity.KEY);
        registerAlias(Generalisation.KEY, Generalisation.KEY);
        registerAlias("generalization", Generalisation.KEY);
        registerAlias("generalization_alignment", Generalisation.KEY);
    }

    private final ConformanceMetric metric;
    private final MetricScope scope;

    ConformanceMetricCatalog(ConformanceMetric metric, MetricScope scope) {
        this.metric = metric;
        this.scope = scope;
    }

    public ConformanceMetric metric() {
        return metric;
    }

    public static Map<String, ConformanceMetric> metricsByKey() {
        return Collections.unmodifiableMap(METRICS_BY_KEY);
    }

    public static List<String> canonicalizeRequestedMetrics(Iterable<String> requestedMetrics, ConformanceMode mode) {
        if (requestedMetrics == null) {
            throw new IllegalArgumentException("metrics must contain at least one metric");
        }
        Set<String> canonical = new LinkedHashSet<String>();
        for (String requestedMetric : requestedMetrics) {
            String canonicalMetric = canonicalMetricKey(requestedMetric);
            if (canonicalMetric == null) {
                throw new IllegalArgumentException("unsupported metric: " + requestedMetric);
            }
            if (!isMetricAllowedForMode(canonicalMetric, mode)) {
                throw new IllegalArgumentException(
                    "metric " + canonicalMetric + " is not available for conformance_mode=" + mode.key()
                );
            }
            canonical.add(canonicalMetric);
        }
        if (canonical.isEmpty()) {
            throw new IllegalArgumentException("metrics must contain at least one metric");
        }
        return new ArrayList<String>(canonical);
    }

    private static String canonicalMetricKey(String requestedMetric) {
        if (requestedMetric == null || requestedMetric.trim().isEmpty()) {
            return null;
        }
        return ALIASES_TO_KEY.get(requestedMetric.trim().toLowerCase());
    }

    private static boolean isMetricAllowedForMode(String metricKey, ConformanceMode mode) {
        MetricScope scope = SCOPE_BY_KEY.get(metricKey);
        if (scope == null) {
            return false;
        }
        if (scope == MetricScope.ANY) {
            return true;
        }
        return mode != null && mode.isAlignment();
    }

    private static void registerAlias(String alias, String canonicalKey) {
        ALIASES_TO_KEY.put(alias.toLowerCase(), canonicalKey);
    }

    private enum MetricScope {
        ANY,
        ALIGNMENT_ONLY
    }
}
