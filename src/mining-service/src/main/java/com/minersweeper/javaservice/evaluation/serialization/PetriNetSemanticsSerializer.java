package com.minersweeper.javaservice.evaluation.serialization;

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
        java.util.Map<String, String> exportedPlaceIds = exportedNodeIds(pnml, "place");
        List<ArtifactBulkResponse.MarkingEntry> entries = new ArrayList<ArtifactBulkResponse.MarkingEntry>();
        for (Place place : marking.baseSet()) {
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
            result.add(serializeMarking(net, pnml, marking));
        }
        return result;
    }

    public List<ArtifactBulkResponse.TransitionEntry> serializeTransitions(Petrinet net, String pnml) {
        if (net == null) {
            throw new IllegalArgumentException("Petri net is required");
        }
        List<ArtifactBulkResponse.TransitionEntry> transitions = new ArrayList<ArtifactBulkResponse.TransitionEntry>();
        java.util.Map<String, String> exportedTransitionIds = exportedNodeIds(pnml, "transition");
        for (Transition transition : net.getTransitions()) {
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
            if (!transition.isInvisible()) {
                visible++;
            }
        }
        return visible;
    }

    private static java.util.Map<String, String> exportedNodeIds(String pnml, String nodeName) {
        if (pnml == null || pnml.trim().isEmpty()) {
            throw new IllegalArgumentException("Exported PNML is required");
        }
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            Document document = factory.newDocumentBuilder().parse(
                new java.io.ByteArrayInputStream(pnml.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1))
            );
            java.util.Map<String, String> ids = new java.util.HashMap<String, String>();
            NodeList nodes = document.getElementsByTagNameNS("*", nodeName);
            if (nodes.getLength() == 0) {
                nodes = document.getElementsByTagName(nodeName);
            }
            for (int index = 0; index < nodes.getLength(); index++) {
                Element node = (Element) nodes.item(index);
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
