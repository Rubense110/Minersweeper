package com.minersweeper.javaservice.evaluation.conformance.metrics;

import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGenRes;

public class Precision {
    public static double compute(AlignmentPrecGenRes alignment) {
        return alignment.getPrecision();
    }
}