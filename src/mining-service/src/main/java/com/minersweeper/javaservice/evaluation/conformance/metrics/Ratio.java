package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;

public class Ratio implements ConformanceMetric {
    public static final String KEY = "ratio";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        double places = net.getPlaces().size();
        double transitions = net.getTransitions().size();
        if (transitions <= 0.0) {
            return 0.0;
        }
        return places / transitions;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
