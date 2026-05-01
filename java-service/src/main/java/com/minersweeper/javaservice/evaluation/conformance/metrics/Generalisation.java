package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;

public class Generalisation implements ConformanceMetric {
    public static final String KEY = "generalisation";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) throws Exception {
        return computation.getGeneralisation();
    }
}
