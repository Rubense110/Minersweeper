package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.conformance.metrics.ConformanceMetric;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Fitness;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Generalisation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Precision;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Simplicity;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public enum ConformanceMetricCatalog {
    FITNESS(new Fitness()),
    PRECISION_ALIGNMENT(new Precision()),
    GENERALIZATION_ALIGNMENT(new Generalisation()),
    SIMPLICITY_STRUCTURAL(new Simplicity());

    private static final Map<String, ConformanceMetric> METRICS_BY_KEY = new LinkedHashMap<String, ConformanceMetric>();

    static {
        for (ConformanceMetricCatalog entry : values()) {
            METRICS_BY_KEY.put(entry.metric.key(), entry.metric);
        }
    }

    private final ConformanceMetric metric;

    ConformanceMetricCatalog(ConformanceMetric metric) {
        this.metric = metric;
    }

    public ConformanceMetric metric() {
        return metric;
    }

    public static Map<String, ConformanceMetric> metricsByKey() {
        return Collections.unmodifiableMap(METRICS_BY_KEY);
    }
}
