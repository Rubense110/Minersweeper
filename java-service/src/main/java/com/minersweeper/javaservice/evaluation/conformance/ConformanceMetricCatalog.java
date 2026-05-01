package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.conformance.metrics.ConformanceMetric;
import com.minersweeper.javaservice.evaluation.conformance.metrics.CyclComplx;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Fitness;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Generalisation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Joins;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Precision;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Places;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Ratio;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Simplicity;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Splits;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Transitions;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Arcs;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public enum ConformanceMetricCatalog {
    PLACES(new Places(), MetricScope.ANY),
    TRANSITIONS(new Transitions(), MetricScope.ANY),
    ARCS(new Arcs(), MetricScope.ANY),
    CYCL_COMPLX(new CyclComplx(), MetricScope.ANY),
    RATIO(new Ratio(), MetricScope.ANY),
    JOINS(new Joins(), MetricScope.ANY),
    SPLITS(new Splits(), MetricScope.ANY),
    FITNESS(new Fitness(), MetricScope.ANY),
    PRECISION(new Precision(), MetricScope.ANY),
    GENERALISATION(new Generalisation(), MetricScope.ANY),
    SIMPLICITY(new Simplicity(), MetricScope.ANY);

    private static final Map<String, ConformanceMetric> METRICS_BY_KEY = new LinkedHashMap<String, ConformanceMetric>();
    private static final Map<String, MetricScope> SCOPE_BY_KEY = new LinkedHashMap<String, MetricScope>();

    static {
        for (ConformanceMetricCatalog entry : values()) {
            METRICS_BY_KEY.put(entry.metric.key(), entry.metric);
            SCOPE_BY_KEY.put(entry.metric.key(), entry.scope);
        }
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
        String metricKey = requestedMetric.trim();
        if (METRICS_BY_KEY.containsKey(metricKey)) {
            return metricKey;
        }
        return null;
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

    private enum MetricScope {
        ANY,
        ALIGNMENT_ONLY
    }
}
