package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;

public class CyclComplx implements ConformanceMetric {
    public static final String KEY = "cycl_complx";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        double arcs = net.getEdges().size();
        double places = net.getPlaces().size();
        double transitions = net.getTransitions().size();
        return arcs - (places + transitions) + 2.0;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
