package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class Splits implements ConformanceMetric {
    public static final String KEY = "splits";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        int splits = 0;

        for (Place place : net.getPlaces()) {
            if (net.getOutEdges(place).size() > 1) {
                splits += 1;
            }
        }
        for (Transition transition : net.getTransitions()) {
            if (net.getOutEdges(transition).size() > 1) {
                splits += 1;
            }
        }
        return splits;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
