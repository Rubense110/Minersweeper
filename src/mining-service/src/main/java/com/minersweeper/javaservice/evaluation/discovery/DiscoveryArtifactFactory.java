package com.minersweeper.javaservice.evaluation.discovery;

import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import org.processmining.acceptingpetrinet.models.AcceptingPetriNet;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.connections.petrinets.behavioral.FinalMarkingConnection;
import org.processmining.models.connections.petrinets.behavioral.InitialMarkingConnection;
import org.processmining.models.semantics.petrinet.Marking;

public final class DiscoveryArtifactFactory {
    private final PmnlExporter pmnlExporter;

    public DiscoveryArtifactFactory(PmnlExporter pmnlExporter) {
        this.pmnlExporter = pmnlExporter;
    }

    public DiscoveryArtifact fromResultArray(PluginContext context, Object[] resultArray) throws Exception {
        Petrinet net = null;
        Petrinet apnNet = null;
        Marking initial = null;
        List<Marking> explicitFinals = new ArrayList<Marking>();
        Marking apnInitial = null;
        List<Marking> apnFinals = null;

        if (resultArray == null) {
            throw new IllegalStateException("Miner returned null result");
        }

        for (Object item : resultArray) {
            if (item == null) {
                continue;
            }
            if (item instanceof Petrinet) {
                net = (Petrinet) item;
                continue;
            }
            if (item instanceof Marking) {
                if (initial == null) {
                    initial = (Marking) item;
                } else {
                    explicitFinals.add((Marking) item);
                }
                continue;
            }
            if (item instanceof AcceptingPetriNet) {
                AcceptingPetriNet apn = (AcceptingPetriNet) item;
                apnNet = apn.getNet();
                apnInitial = apn.getInitialMarking();
                Set<Marking> acceptingFinals = apn.getFinalMarkings();
                if (acceptingFinals != null) {
                    apnFinals = new ArrayList<Marking>(acceptingFinals);
                }
            }
        }

        if (apnNet != null) {
            net = apnNet;
        }
        if (net == null) {
            throw new IllegalStateException("Unable to extract Petri net from miner result");
        }

        Marking initialMarking = apnInitial != null ? apnInitial : initial;
        if (initialMarking == null) {
            initialMarking = initialMarkingFromConnection(context, net);
        }
        List<Marking> finalMarkings = apnFinals != null ? apnFinals : explicitFinals;
        if (finalMarkings.isEmpty()) {
            finalMarkings = finalMarkingsFromConnections(context, net);
        }
        if (initialMarking == null || finalMarkings.isEmpty()) {
            throw new IllegalStateException("Miner result has no accepting Petri-net semantics (initial/final marking)");
        }
        final Petrinet exportedNet = net;
        return new DiscoveryArtifact(net, initialMarking, finalMarkings,
            () -> pmnlExporter.exportPnml(context, exportedNet));
    }

    private Marking initialMarkingFromConnection(PluginContext context, Petrinet net) throws Exception {
        if (context == null) {
            return null;
        }
        Collection<InitialMarkingConnection> connections = context.getConnectionManager().getConnections(
            InitialMarkingConnection.class, context, net
        );
        for (InitialMarkingConnection connection : connections) {
            Marking marking = connection.getObjectWithRole("Marking");
            if (marking != null) {
                return marking;
            }
        }
        return null;
    }

    private List<Marking> finalMarkingsFromConnections(PluginContext context, Petrinet net) throws Exception {
        List<Marking> markings = new ArrayList<Marking>();
        if (context == null) {
            return markings;
        }
        Collection<FinalMarkingConnection> connections = context.getConnectionManager().getConnections(
            FinalMarkingConnection.class, context, net
        );
        for (FinalMarkingConnection connection : connections) {
            Marking marking = connection.getObjectWithRole(FinalMarkingConnection.MARKING);
            if (marking != null) {
                markings.add(marking);
            }
        }
        return markings;
    }
}
