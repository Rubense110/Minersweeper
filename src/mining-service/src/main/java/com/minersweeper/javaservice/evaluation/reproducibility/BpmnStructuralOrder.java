package com.minersweeper.javaservice.evaluation.reproducibility;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import com.minersweeper.javaservice.evaluation.ReproducibilityException;
import java.util.*;
import org.processmining.models.graphbased.directed.bpmn.*;
import org.processmining.models.graphbased.directed.bpmn.elements.*;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.*;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

/** Structural ranks for Split's flat BPMN; the auxiliary net is never evaluated. */
public final class BpmnStructuralOrder {
    private final Map<BPMNNode,Integer> ranks = new IdentityHashMap<BPMNNode,Integer>();

    public BpmnStructuralOrder(BPMNDiagram diagram) {
        Petrinet encoding = PetrinetFactory.newPetrinet("BPMN ordering only");
        Map<BPMNNode,Place> nodes = new IdentityHashMap<BPMNNode,Place>();
        for (BPMNNode node : diagram.getNodes()) {
            ExecutionChecks.check();
            Place place = encoding.addPlace("");
            nodes.put(node, place);
            Transition marker = encoding.addTransition("NODE:" + color(node));
            Place leaf = encoding.addPlace("");
            encoding.addArc(place, marker);
            encoding.addArc(marker, leaf);
        }
        for (Flow flow : diagram.getFlows()) {
            ExecutionChecks.check();
            Transition edge = encoding.addTransition("FLOW:" + field(flow.getLabel())
                + field(flow.getConditionExpression()));
            encoding.addArc(nodes.get(flow.getSource()), edge);
            encoding.addArc(edge, nodes.get(flow.getTarget()));
        }
        CanonicalNetOrder order = new CanonicalNetOrder(encoding, new Marking(),
            Collections.<Marking>emptyList());
        for (Map.Entry<BPMNNode,Place> node : nodes.entrySet())
            ranks.put(node.getKey(), order.index(node.getValue()));
    }

    public int index(BPMNNode node) { return ranks.get(node); }

    public <N extends BPMNNode> Comparator<N> comparator() {
        return (a, b) -> Integer.compare(index(a), index(b));
    }

    private static String field(String text) {
        return text == null ? "-1:" : text.length() + ":" + text;
    }

    private static String color(BPMNNode node) {
        if (node instanceof Activity) {
            Activity a = (Activity)node;
            return "Activity:" + field(a.getLabel()) + ":" + a.isBLooped() + ":"
                + a.isBAdhoc() + ":" + a.isBCompensation() + ":" + a.isBMultiinstance()
                + ":" + a.isBCollapsed();
        }
        if (node instanceof Gateway) return "Gateway:" + ((Gateway)node).getGatewayType();
        if (node instanceof Event) {
            Event e = (Event)node;
            return "Event:" + e.getEventType() + ":" + e.getEventTrigger() + ":"
                + e.getEventUse() + ":" + e.isInterrupting() + ":" + e.getParallelMultiple();
        }
        throw new ReproducibilityException("REPRODUCIBILITY_SPLIT_UNSUPPORTED_BPMN");
    }
}
