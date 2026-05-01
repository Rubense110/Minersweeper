package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;

public class Arcs implements ConformanceMetric {
    public static final String KEY = "arcs";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        return computation.getNet().getEdges().size();
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
