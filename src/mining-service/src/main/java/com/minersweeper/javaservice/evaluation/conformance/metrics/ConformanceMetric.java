package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;

public interface ConformanceMetric {
    String key();

    double compute(ConformanceComputation computation) throws Exception;

    default boolean boundedUnitInterval() {
        return true;
    }
}
