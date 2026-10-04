package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import com.minersweeper.javaservice.evaluation.reproducibility.CanonicalNetOrder;
import org.processmining.models.semantics.petrinet.Marking;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

/** Net topology compiled once and shared by fitness/final-marking/precision engines. */
public final class CompiledReplayNet {
    final List<Transition> transitions;
    final CanonicalNetOrder order;
    final Map<Transition, List<Arc>> inputs = new HashMap<Transition, List<Arc>>();
    final Map<Transition, List<Arc>> outputs = new HashMap<Transition, List<Arc>>();
    final Map<Transition, List<Place>> targets = new HashMap<Transition, List<Place>>();
    final Map<Place, List<Transition>> hiddenSuccessors = new HashMap<Place, List<Transition>>();
    final Map<Place, Integer> placeIndexes = new HashMap<Place, Integer>();

    public CompiledReplayNet(Petrinet net) {
        this(net, null, Collections.<Marking>emptyList());
    }

    public CompiledReplayNet(Petrinet net, Marking initial, List<Marking> finals) {
        order = new CanonicalNetOrder(net, initial, finals);
        List<Transition> ordered = order.transitions();
        transitions = Collections.unmodifiableList(ordered);
        for (Place place : order.places()) {
            ExecutionChecks.check();
            placeIndexes.put(place, placeIndexes.size());
            List<Transition> hidden = new ArrayList<Transition>();
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(place)) {
                ExecutionChecks.check();
                if (edge.getTarget() instanceof Transition && ((Transition) edge.getTarget()).isInvisible()) {
                    hidden.add((Transition) edge.getTarget());
                }
            }
            Collections.sort(hidden, order.<Transition>comparator());
            hiddenSuccessors.put(place, Collections.unmodifiableList(hidden));
        }
        for (Transition transition : transitions) {
            ExecutionChecks.check();
            List<Arc> in = new ArrayList<Arc>(), out = new ArrayList<Arc>();
            List<Place> places = new ArrayList<Place>();
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(transition)) {
                if (edge instanceof Arc && edge.getSource() instanceof Place) in.add((Arc) edge);
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(transition)) {
                if (edge instanceof Arc && edge.getTarget() instanceof Place) {
                    out.add((Arc) edge); places.add((Place) edge.getTarget());
                }
            }
            Collections.sort(places, order.<Place>comparator());
            Collections.sort(in, java.util.Comparator.comparingInt(a -> order.index(a.getSource())));
            Collections.sort(out, java.util.Comparator.comparingInt(a -> order.index(a.getTarget())));
            inputs.put(transition, Collections.unmodifiableList(in));
            outputs.put(transition, Collections.unmodifiableList(out));
            targets.put(transition, Collections.unmodifiableList(places));
        }
    }
}
