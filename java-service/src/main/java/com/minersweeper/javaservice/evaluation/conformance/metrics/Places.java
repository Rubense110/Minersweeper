package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;

public class Places implements ConformanceMetric {
    public static final String KEY = "places";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        return computation.getNet().getPlaces().size();
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
