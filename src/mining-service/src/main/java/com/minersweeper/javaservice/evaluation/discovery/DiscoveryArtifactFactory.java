package com.minersweeper.javaservice.evaluation.discovery;

import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import org.processmining.acceptingpetrinet.models.AcceptingPetriNet;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.semantics.petrinet.Marking;

public final class DiscoveryArtifactFactory {
    private final PmnlExporter pmnlExporter;

    public DiscoveryArtifactFactory(PmnlExporter pmnlExporter) {
        this.pmnlExporter = pmnlExporter;
    }

    public DiscoveryArtifact fromResultArray(PluginContext context, Object[] resultArray) throws Exception {
        Petrinet net = null;
        Marking initial = null;
        Marking fin = null;
        List<Marking> finals = new ArrayList<Marking>();

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
                } else if (fin == null) {
                    fin = (Marking) item;
                    finals.add(fin);
                }
                continue;
            }
            if (item instanceof AcceptingPetriNet) {
                AcceptingPetriNet apn = (AcceptingPetriNet) item;
                net = apn.getNet();
                initial = apn.getInitialMarking();
                Set<Marking> acceptingFinals = apn.getFinalMarkings();
                if (acceptingFinals != null && !acceptingFinals.isEmpty()) {
                    finals.clear();
                    for (Marking acceptingFinal : acceptingFinals) {
                        if (!isEmptyMarking(acceptingFinal)) {
                            finals.add(acceptingFinal);
                        }
                    }
                    if (!finals.isEmpty()) {
                        fin = finals.get(0);
                    }
                }
            }
        }

        if (net == null) {
            throw new IllegalStateException("Unable to extract Petri net from miner result");
        }

        Marking initialMarking = isEmptyMarking(initial) ? deriveInitialMarking(net) : initial;
        List<Marking> finalMarkings = finals.isEmpty()
            ? Collections.singletonList(isEmptyMarking(fin) ? deriveFinalMarking(net) : fin)
            : finals;
        String pnml = pmnlExporter.exportPnml(context, net);
        return new DiscoveryArtifact(net, initialMarking, finalMarkings, pnml);
    }

    private static boolean isEmptyMarking(Marking marking) {
        return marking == null || marking.isEmpty();
    }

    private Marking deriveInitialMarking(Petrinet net) {
        Marking marking = new Marking();
        for (Place place : net.getPlaces()) {
            if (net.getInEdges(place).isEmpty()) {
                marking.add(place);
            }
        }
        if (marking.isEmpty() && !net.getPlaces().isEmpty()) {
            marking.add(net.getPlaces().iterator().next());
        }
        return marking;
    }

    private Marking deriveFinalMarking(Petrinet net) {
        Marking marking = new Marking();
        for (Place place : net.getPlaces()) {
            if (net.getOutEdges(place).isEmpty()) {
                marking.add(place);
            }
        }
        if (marking.isEmpty() && !net.getPlaces().isEmpty()) {
            marking.add(net.getPlaces().iterator().next());
        }
        return marking;
    }
}
