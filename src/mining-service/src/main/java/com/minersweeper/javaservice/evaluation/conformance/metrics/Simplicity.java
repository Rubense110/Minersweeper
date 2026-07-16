package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class Simplicity implements ConformanceMetric {
    public static final String KEY = "simplicity";
    private static final double DEFAULT_BASELINE_ARC_DEGREE = 2.0;

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        return computeStructuralSimplicity(computation.getNet());
    }

    private double computeStructuralSimplicity(Petrinet net) {
        double totalArcDegree = 0.0;
        int nodeCount = 0;

        for (Place place : net.getPlaces()) {
            totalArcDegree += net.getInEdges(place).size() + net.getOutEdges(place).size();
            nodeCount++;
        }
        for (Transition transition : net.getTransitions()) {
            totalArcDegree += net.getInEdges(transition).size() + net.getOutEdges(transition).size();
            nodeCount++;
        }

        double meanArcDegree = nodeCount == 0 ? 0.0 : totalArcDegree / nodeCount;
        return 1.0 / (1.0 + Math.max(meanArcDegree - DEFAULT_BASELINE_ARC_DEGREE, 0.0));
    }
}
