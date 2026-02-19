package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class Simplicity implements ConformanceMetric {
    public static final String KEY = "simplicity_structural";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        return computeStructuralSimplicity(computation.getNet());
    }

    private double computeStructuralSimplicity(Petrinet net) {
        double places = net.getPlaces().size();
        double transitions = net.getTransitions().size();
        double arcs = net.getEdges().size();

        double branchingPenalty = 0.0;
        for (Transition transition : net.getTransitions()) {
            int in = net.getInEdges(transition).size();
            int out = net.getOutEdges(transition).size();
            if (in > 1) {
                branchingPenalty += (in - 1);
            }
            if (out > 1) {
                branchingPenalty += (out - 1);
            }
        }

        double complexity = places + transitions + arcs + branchingPenalty;
        return 1.0 / (1.0 + (complexity / 50.0));
    }
}
