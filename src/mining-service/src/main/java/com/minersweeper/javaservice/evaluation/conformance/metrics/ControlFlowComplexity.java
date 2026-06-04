package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class ControlFlowComplexity implements ConformanceMetric {
    public static final String KEY = "cfc";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        int complexity = 0;

        for (Place place : net.getPlaces()) {
            int outDegree = net.getOutEdges(place).size();
            if (outDegree > 1) {
                complexity += outDegree;
            }
        }
        for (Transition transition : net.getTransitions()) {
            if (net.getOutEdges(transition).size() > 1) {
                complexity += 1;
            }
        }
        return complexity;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
