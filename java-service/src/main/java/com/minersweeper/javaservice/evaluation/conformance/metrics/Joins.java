package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class Joins implements ConformanceMetric {
    public static final String KEY = "joins";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        int joins = 0;

        for (Place place : net.getPlaces()) {
            if (net.getInEdges(place).size() > 1) {
                joins += 1;
            }
        }
        for (Transition transition : net.getTransitions()) {
            if (net.getInEdges(transition).size() > 1) {
                joins += 1;
            }
        }
        return joins;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }
}
