package com.minersweeper.javaservice.evaluation.io;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.io.StringWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamWriter;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;

/** Writes ordinary weighted Petri nets without mutating labels or relying on ProM's XML escaping. */
public class PmnlExporter {
    /** Graph-only export; accepting semantics are supplied explicitly by DiscoveryArtifactFactory. */
    public String exportPnml(PluginContext context, Petrinet net) throws Exception {
        return exportPnml(context, net, null, Collections.<Marking>emptyList());
    }

    public String exportPnml(PluginContext context, Petrinet net, Marking initial,
        List<Marking> finals) throws Exception {
        if (net == null || finals == null) throw new IllegalArgumentException("Petri net and final markings are required");
        List<Place> places = ordered(net.getPlaces());
        List<Transition> transitions = ordered(net.getTransitions());
        Map<PetrinetNode, String> ids = new IdentityHashMap<PetrinetNode, String>();
        for (int i = 0; i < places.size(); i++) ids.put(places.get(i), "p" + (i + 1));
        for (int i = 0; i < transitions.size(); i++) ids.put(transitions.get(i), "t" + (i + 1));
        validateMarking(initial, ids);
        for (Marking marking : finals) {
            if (marking == null) throw new IllegalArgumentException("Final marking must not be null");
            validateMarking(marking, ids);
        }

        StringWriter output = new StringWriter();
        XMLStreamWriter xml = XMLOutputFactory.newFactory().createXMLStreamWriter(output);
        try {
            xml.writeStartDocument("UTF-8", "1.0");
            xml.writeStartElement("pnml");
            xml.writeStartElement("net");
            xml.writeAttribute("id", "net1");
            xml.writeAttribute("type", "http://www.pnml.org/version-2009/grammar/ptnet");
            textElement(xml, "name", net.getLabel());
            xml.writeStartElement("page");
            xml.writeAttribute("id", "page1");
            for (Place place : places) {
                ExecutionChecks.check();
                xml.writeStartElement("place");
                xml.writeAttribute("id", ids.get(place));
                textElement(xml, "name", place.getLabel());
                provenance(xml, place, null);
                if (initial != null && initial.occurrences(place).intValue() > 0)
                    textElement(xml, "initialMarking", initial.occurrences(place).toString());
                xml.writeEndElement();
            }
            for (Transition transition : transitions) {
                ExecutionChecks.check();
                xml.writeStartElement("transition");
                xml.writeAttribute("id", ids.get(transition));
                textElement(xml, "name", transition.getLabel());
                provenance(xml, transition, transition.isInvisible() ? "$invisible$" : transition.getLabel());
                xml.writeEndElement();
            }
            List<Arc> arcs = new ArrayList<Arc>();
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getEdges()) {
                ExecutionChecks.check();
                if (!(edge instanceof Arc)) throw new IllegalArgumentException("PNML export requires ordinary weighted arcs");
                if (!ids.containsKey(edge.getSource()) || !ids.containsKey(edge.getTarget()))
                    throw new IllegalArgumentException("Arc endpoint is not in the exported net");
                arcs.add((Arc) edge);
            }
            Collections.sort(arcs, Comparator.comparing((Arc a) -> ids.get(a.getSource()))
                .thenComparing(a -> ids.get(a.getTarget())).thenComparingInt(Arc::getWeight));
            for (int i = 0; i < arcs.size(); i++) {
                ExecutionChecks.check();
                Arc arc = arcs.get(i);
                xml.writeStartElement("arc");
                xml.writeAttribute("id", "a" + (i + 1));
                xml.writeAttribute("source", ids.get(arc.getSource()));
                xml.writeAttribute("target", ids.get(arc.getTarget()));
                textElement(xml, "inscription", Integer.toString(arc.getWeight()));
                xml.writeEndElement();
            }
            xml.writeEndElement(); // page
            xml.writeStartElement("finalmarkings");
            for (Marking marking : finals) {
                ExecutionChecks.check();
                xml.writeStartElement("marking");
                for (Place place : ordered(marking.baseSet())) {
                    ExecutionChecks.check();
                    int tokens = marking.occurrences(place).intValue();
                    if (tokens <= 0) continue;
                    xml.writeStartElement("place");
                    xml.writeAttribute("idref", ids.get(place));
                    xml.writeStartElement("text");
                    xml.writeCharacters(Integer.toString(tokens));
                    xml.writeEndElement();
                    xml.writeEndElement();
                }
                xml.writeEndElement();
            }
            xml.writeEndElement(); // finalmarkings
            xml.writeEndElement(); // net
            xml.writeEndElement(); // pnml
            xml.writeEndDocument();
            xml.flush();
            return output.toString();
        } finally {
            xml.close();
        }
    }

    private static <T extends PetrinetNode> List<T> ordered(java.util.Collection<T> nodes) {
        List<T> result = new ArrayList<T>(nodes);
        // These IDs identify the exact artifact; scientific identity is CanonicalNetOrder's hash.
        Collections.sort(result, Comparator.comparing(n -> n.getLocalID().toString()));
        return result;
    }

    private static void validateMarking(Marking marking, Map<PetrinetNode, String> ids) {
        if (marking == null) return;
        for (Place place : marking.baseSet()) {
            ExecutionChecks.check();
            if (!ids.containsKey(place) || marking.occurrences(place).intValue() <= 0)
                throw new IllegalArgumentException("Marking contains an invalid place or token count");
        }
    }

    private static void provenance(XMLStreamWriter xml, PetrinetNode node, String activity) throws Exception {
        xml.writeEmptyElement("toolspecific");
        xml.writeAttribute("tool", "ProM");
        xml.writeAttribute("version", "6.4");
        xml.writeAttribute("localNodeID", node.getLocalID().toString());
        if (activity != null) xml.writeAttribute("activity", activity);
    }

    private static void textElement(XMLStreamWriter xml, String element, String value) throws Exception {
        xml.writeStartElement(element);
        xml.writeStartElement("text");
        xml.writeCharacters(value == null ? "" : value);
        xml.writeEndElement();
        xml.writeEndElement();
    }
}
