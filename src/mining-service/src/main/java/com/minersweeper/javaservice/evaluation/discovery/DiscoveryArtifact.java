package com.minersweeper.javaservice.evaluation.discovery;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.semantics.petrinet.Marking;

public final class DiscoveryArtifact {
    private final Petrinet net;
    private final Marking initialMarking;
    private final Marking evaluationFinalMarking;
    private final List<Marking> finalMarkings;
    private String pnml;
    private java.util.concurrent.Callable<String> exporter;
    private java.util.Map<String,String> discoveryMetadata = java.util.Collections.emptyMap();

    public DiscoveryArtifact withDiscoveryMetadata(java.util.Map<String,String> metadata) {
        discoveryMetadata = java.util.Collections.unmodifiableMap(
            new java.util.LinkedHashMap<String,String>(metadata));
        return this;
    }

    public java.util.Map<String,String> getDiscoveryMetadata() { return discoveryMetadata; }

    public DiscoveryArtifact(Petrinet net, Marking initialMarking, Marking finalMarking, String pnml) {
        this(net, initialMarking, finalMarking == null ? Collections.emptyList() : Collections.singletonList(finalMarking), pnml);
    }

    public DiscoveryArtifact(Petrinet net, Marking initialMarking, List<Marking> finalMarkings, String pnml) {
        if (net == null || initialMarking == null || finalMarkings == null || finalMarkings.isEmpty()) {
            throw new IllegalArgumentException("Discovery artifact requires Petri-net semantics");
        }
        this.net = net;
        this.initialMarking = initialMarking;
        this.finalMarkings = finalMarkings == null
            ? Collections.emptyList()
            : Collections.unmodifiableList(new ArrayList<Marking>(finalMarkings));
        this.evaluationFinalMarking = this.finalMarkings.get(0);
        this.pnml = pnml;
    }

    public DiscoveryArtifact(Petrinet net, Marking initial, List<Marking> finals,
        java.util.concurrent.Callable<String> exporter) {
        this(net, initial, finals, (String) null);
        this.exporter = exporter;
    }

    public Petrinet getNet() {
        return net;
    }

    public Marking getInitialMarking() {
        return initialMarking;
    }

    public Marking getFinalMarking() {
        return evaluationFinalMarking;
    }

    public List<Marking> getFinalMarkings() {
        return finalMarkings;
    }

    public synchronized String getPnml() {
        if (pnml == null && exporter != null) {
            try { pnml = exporter.call(); exporter = null; }
            catch (Exception error) { throw new IllegalStateException("PNML export failed", error); }
        }
        return pnml;
    }
}
