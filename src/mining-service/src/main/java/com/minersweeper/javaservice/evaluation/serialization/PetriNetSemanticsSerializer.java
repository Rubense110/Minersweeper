package com.minersweeper.javaservice.evaluation.serialization;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import javax.xml.parsers.DocumentBuilderFactory;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

/** Serializes the semantics attached to the exact net used for evaluation. */
public final class PetriNetSemanticsSerializer {
    public List<ArtifactBulkResponse.MarkingEntry> serializeMarking(Petrinet net, String pnml, Marking marking) {
        if (net == null || marking == null) {
            throw new IllegalArgumentException("Petri net and marking are required");
        }
        Set<Place> netPlaces = new HashSet<Place>(net.getPlaces());
        return serializeMarking(net, marking, netPlaces, exportedNodeIds(parseDocument(pnml), "place"));
    }

    private List<ArtifactBulkResponse.MarkingEntry> serializeMarking(Petrinet net, Marking marking,
        Set<Place> netPlaces, java.util.Map<String, String> exportedPlaceIds) {
        List<ArtifactBulkResponse.MarkingEntry> entries = new ArrayList<ArtifactBulkResponse.MarkingEntry>();
        for (Place place : marking.baseSet()) {
            ExecutionChecks.check();
            if (place == null || !netPlaces.contains(place) || place.getLocalID() == null) {
                throw new IllegalStateException("Marking contains a place not exported by the Petri net");
            }
            int tokens = marking.occurrences(place).intValue();
            if (tokens <= 0) {
                throw new IllegalStateException("Marking contains a non-positive token count");
            }
            String placeId = exportedPlaceIds.get(place.getLocalID().toString());
            if (placeId == null) {
                throw new IllegalStateException("Marking place is missing from exported PNML");
            }
            entries.add(new ArtifactBulkResponse.MarkingEntry(placeId, tokens));
        }
        Collections.sort(entries, new Comparator<ArtifactBulkResponse.MarkingEntry>() {
            @Override
            public int compare(ArtifactBulkResponse.MarkingEntry left, ArtifactBulkResponse.MarkingEntry right) {
                return left.place_id.compareTo(right.place_id);
            }
        });
        return entries;
    }

    public List<List<ArtifactBulkResponse.MarkingEntry>> serializeFinalMarkings(Petrinet net, String pnml, List<Marking> markings) {
        List<List<ArtifactBulkResponse.MarkingEntry>> result = new ArrayList<List<ArtifactBulkResponse.MarkingEntry>>();
        if (markings == null) {
            throw new IllegalArgumentException("Final markings are required");
        }
        for (Marking marking : markings) {
            ExecutionChecks.check();
            result.add(serializeMarking(net, pnml, marking));
        }
        return result;
    }

    public List<ArtifactBulkResponse.TransitionEntry> serializeTransitions(Petrinet net, String pnml) {
        if (net == null) {
            throw new IllegalArgumentException("Petri net is required");
        }
        return serializeTransitions(net, exportedNodeIds(parseDocument(pnml), "transition"));
    }

    private List<ArtifactBulkResponse.TransitionEntry> serializeTransitions(Petrinet net,
        java.util.Map<String, String> exportedTransitionIds) {
        List<ArtifactBulkResponse.TransitionEntry> transitions = new ArrayList<ArtifactBulkResponse.TransitionEntry>();
        for (Transition transition : net.getTransitions()) {
            ExecutionChecks.check();
            if (transition == null || transition.getLocalID() == null) {
                throw new IllegalStateException("Petri net contains a transition without an ID");
            }
            String transitionId = exportedTransitionIds.get(transition.getLocalID().toString());
            if (transitionId == null) {
                throw new IllegalStateException("Transition is missing from exported PNML");
            }
            transitions.add(new ArtifactBulkResponse.TransitionEntry(
                transitionId,
                transition.getLabel(),
                transition.isInvisible()
            ));
        }
        Collections.sort(transitions, new Comparator<ArtifactBulkResponse.TransitionEntry>() {
            @Override
            public int compare(ArtifactBulkResponse.TransitionEntry left, ArtifactBulkResponse.TransitionEntry right) {
                return left.id.compareTo(right.id);
            }
        });
        return transitions;
    }

    public int countVisibleTransitions(Petrinet net) {
        if (net == null) {
            throw new IllegalArgumentException("Petri net is required");
        }
        int visible = 0;
        for (Transition transition : net.getTransitions()) {
            ExecutionChecks.check();
            if (!transition.isInvisible()) {
                visible++;
            }
        }
        return visible;
    }

    public SerializedSemantics serializeAll(Petrinet net, String pnml, Marking initial, List<Marking> finals) {
        if (net == null || initial == null || finals == null || finals.isEmpty())
            throw new IllegalArgumentException("Petri net and accepting markings are required");
        Document document = parseDocument(pnml);
        java.util.Map<String, String> placeIds = exportedNodeIds(document, "place");
        Set<Place> places = new HashSet<Place>(net.getPlaces());
        List<List<ArtifactBulkResponse.MarkingEntry>> finalPayload = new ArrayList<List<ArtifactBulkResponse.MarkingEntry>>();
        for (Marking marking : finals) finalPayload.add(serializeMarking(net, marking, places, placeIds));
        return new SerializedSemantics(serializeMarking(net, initial, places, placeIds), finalPayload,
            serializeTransitions(net, exportedNodeIds(document, "transition")));
    }

    public static final class SerializedSemantics {
        public final List<ArtifactBulkResponse.MarkingEntry> initial;
        public final List<List<ArtifactBulkResponse.MarkingEntry>> finals;
        public final List<ArtifactBulkResponse.TransitionEntry> transitions;
        SerializedSemantics(List<ArtifactBulkResponse.MarkingEntry> initial,
            List<List<ArtifactBulkResponse.MarkingEntry>> finals, List<ArtifactBulkResponse.TransitionEntry> transitions) {
            this.initial = initial; this.finals = finals; this.transitions = transitions;
        }
    }

    private static Document parseDocument(String pnml) {
        if (pnml == null || pnml.trim().isEmpty()) throw new IllegalArgumentException("Exported PNML is required");
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            return factory.newDocumentBuilder().parse(new org.xml.sax.InputSource(new java.io.StringReader(pnml)));
        } catch (Exception error) {
            throw new IllegalStateException("Unable to parse exported PNML", error);
        }
    }

    private static java.util.Map<String, String> exportedNodeIds(Document document, String nodeName) {
        try {
            java.util.Map<String, String> ids = new java.util.HashMap<String, String>();
            NodeList nodes = document.getElementsByTagNameNS("*", nodeName);
            if (nodes.getLength() == 0) {
                nodes = document.getElementsByTagName(nodeName);
            }
            for (int index = 0; index < nodes.getLength(); index++) {
                ExecutionChecks.check();
                Element node = (Element) nodes.item(index);
                // Final-marking references are not net node declarations.
                if (node.hasAttribute("idref")) continue;
                String exportedId = node.getAttribute("id");
                String localNodeId = localNodeId(node);
                if (exportedId == null || exportedId.isEmpty() || localNodeId == null || ids.put(localNodeId, exportedId) != null) {
                    throw new IllegalStateException("PNML node IDs cannot be mapped unambiguously");
                }
            }
            return ids;
        } catch (IllegalStateException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("Unable to map ProM nodes to exported PNML IDs", error);
        }
    }

    private static String localNodeId(Element node) {
        NodeList descendants = node.getElementsByTagNameNS("*", "toolspecific");
        if (descendants.getLength() == 0) {
            descendants = node.getElementsByTagName("toolspecific");
        }
        for (int index = 0; index < descendants.getLength(); index++) {
            ExecutionChecks.check();
            Node descendant = descendants.item(index);
            if (descendant instanceof Element) {
                String value = ((Element) descendant).getAttribute("localNodeID");
                if (value != null && !value.isEmpty()) {
                    return value;
                }
            }
        }
        return null;
    }
}
