package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;

public class Transitions implements ConformanceMetric {
    public static final String KEY = "transitions";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        return computation.getNet().getTransitions().size();
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
