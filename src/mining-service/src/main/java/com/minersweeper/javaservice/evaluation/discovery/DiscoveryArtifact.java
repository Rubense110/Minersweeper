package com.minersweeper.javaservice.evaluation.discovery;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.semantics.petrinet.Marking;

public final class DiscoveryArtifact {
    private final Petrinet net;
    private final Marking initialMarking;
    private final List<Marking> finalMarkings;
    private final String pnml;

    public DiscoveryArtifact(Petrinet net, Marking initialMarking, Marking finalMarking, String pnml) {
        this(net, initialMarking, finalMarking == null ? Collections.emptyList() : Collections.singletonList(finalMarking), pnml);
    }

    public DiscoveryArtifact(Petrinet net, Marking initialMarking, List<Marking> finalMarkings, String pnml) {
        this.net = net;
        this.initialMarking = initialMarking;
        this.finalMarkings = finalMarkings == null
            ? Collections.emptyList()
            : Collections.unmodifiableList(new ArrayList<Marking>(finalMarkings));
        this.pnml = pnml;
    }

    public Petrinet getNet() {
        return net;
    }

    public Marking getInitialMarking() {
        return initialMarking;
    }

    public Marking getFinalMarking() {
        if (finalMarkings.isEmpty()) {
            return null;
        }
        return finalMarkings.get(0);
    }

    public List<Marking> getFinalMarkings() {
        return finalMarkings;
    }

    public String getPnml() {
        return pnml;
    }
}
