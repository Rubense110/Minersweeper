package com.minersweeper.javaservice.evaluation.discovery;

import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.semantics.petrinet.Marking;

public final class DiscoveryArtifact {
    private final Petrinet net;
    private final Marking initialMarking;
    private final Marking finalMarking;
    private final String pnml;

    public DiscoveryArtifact(Petrinet net, Marking initialMarking, Marking finalMarking, String pnml) {
        this.net = net;
        this.initialMarking = initialMarking;
        this.finalMarking = finalMarking;
        this.pnml = pnml;
    }

    public Petrinet getNet() {
        return net;
    }

    public Marking getInitialMarking() {
        return initialMarking;
    }

    public Marking getFinalMarking() {
        return finalMarking;
    }

    public String getPnml() {
        return pnml;
    }
}
