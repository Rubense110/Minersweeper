package com.minersweeper.javaservice.evaluation.conformance.metrics;

import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGenRes;

public class Generalisation {
    public static double compute(AlignmentPrecGenRes alignment) {
        return alignment.getGeneralization();
    }
}