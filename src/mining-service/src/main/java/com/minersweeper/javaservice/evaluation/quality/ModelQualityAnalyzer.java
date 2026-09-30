package com.minersweeper.javaservice.evaluation.quality;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import com.minersweeper.javaservice.evaluation.quality.ReachabilitySupport.*;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;

/** Bounded, unrepaired reachability diagnostics on the original discovered net. */
public final class ModelQualityAnalyzer {
    private static final int DEFAULT_MAX_STATES = 5000;
    private static final int DEFAULT_MAX_TOKENS_PER_PLACE = 10;
    private static final long DEFAULT_MAX_NANOS = 2_000_000_000L;

    private final int maxStates;
    private final int maxTokensPerPlace;
    private final long maxNanos;

    public ModelQualityAnalyzer() {
        this(DEFAULT_MAX_STATES, DEFAULT_MAX_TOKENS_PER_PLACE, DEFAULT_MAX_NANOS);
    }

    public ModelQualityAnalyzer(int maxStates, int maxTokensPerPlace, long maxNanos) {
        if (maxStates < 1 || maxTokensPerPlace < 1 || maxNanos < 1) {
            throw new IllegalArgumentException("Quality analysis limits must be positive");
        }
        this.maxStates = maxStates;
        this.maxTokensPerPlace = maxTokensPerPlace;
        this.maxNanos = maxNanos;
    }

    public static final class Result {
        public final List<String> defects;
        public final boolean multipleComponents;
        public final boolean inconclusive;
        public final int exploredStates;

        Result(List<String> defects, boolean multipleComponents, boolean inconclusive, int exploredStates) {
            this.defects = Collections.unmodifiableList(new ArrayList<String>(defects));
            this.multipleComponents = multipleComponents;
            this.inconclusive = inconclusive;
            this.exploredStates = exploredStates;
        }

        public List<String> violations() {
            LinkedHashSet<String> reasons = new LinkedHashSet<String>(defects);
            if (multipleComponents) reasons.add("MULTIPLE_COMPONENTS");
            if (inconclusive) reasons.add("QUALITY_CHECK_INCONCLUSIVE");
            return Collections.unmodifiableList(new ArrayList<String>(reasons));
        }
    }

    private static final class Step {
        final StateKey target;
        final boolean visible;

        Step(StateKey target, boolean visible) {
            this.target = target;
            this.visible = visible;
        }
    }

    public Result analyze(Petrinet net, Marking initial, List<Marking> finals) {
        Budget budget = new Budget(maxNanos);
        try {
            return analyzeBounded(net, initial, finals, budget);
        } catch (Inconclusive | ArithmeticException limit) {
            return new Result(Collections.<String>emptyList(), budget.multipleComponents, true, budget.states);
        }
    }

    private Result analyzeBounded(Petrinet net, Marking initial, List<Marking> finals, Budget budget) {
        budget.check();
        if (net == null || initial == null || finals == null) {
            throw new IllegalArgumentException("Net and markings are required");
        }

        List<Place> places = new ArrayList<Place>(net.getPlaces());
        List<Transition> transitions = new ArrayList<Transition>(net.getTransitions());
        Map<Place, Integer> placeIndex = new HashMap<Place, Integer>();
        for (int index = 0; index < places.size(); index++) {
            budget.check();
            placeIndex.put(places.get(index), Integer.valueOf(index));
        }
        boolean multipleComponents = hasMultipleComponents(net, places, transitions, budget);
        budget.multipleComponents = multipleComponents;
        LinkedHashSet<String> defects = new LinkedHashSet<String>();
        int visibleCount = 0;
        for (Transition transition : transitions) { budget.check(); if (!transition.isInvisible()) visibleCount++; }
        if (visibleCount == 0) defects.add("NO_VISIBLE_TRANSITIONS");
        if (finals.size() != 1) defects.add("MULTIPLE_FINAL_MARKINGS");
        if (!defects.isEmpty()) return new Result(new ArrayList<String>(defects), multipleComponents, false, 0);

        int[] start = markingVector(initial, places, placeIndex, budget);
        int[] fin = markingVector(finals.get(0), places, placeIndex, budget);
        if (exceedsTokenLimit(start, budget) || exceedsTokenLimit(fin, budget)) {
            return new Result(Collections.<String>emptyList(), multipleComponents, true, 0);
        }
        SparseNet topology = new SparseNet(net, places, transitions, budget);

        StateKey startKey = new StateKey(start);
        StateKey finalKey = new StateKey(fin);
        Map<StateKey, int[]> states = new LinkedHashMap<StateKey, int[]>();
        Map<StateKey, List<Step>> graph = new LinkedHashMap<StateKey, List<Step>>();
        ArrayDeque<StateKey> queue = new ArrayDeque<StateKey>();
        states.put(startKey, start);
        queue.add(startKey);
        Set<Transition> fired = new HashSet<Transition>();
        budget.states = states.size();
        boolean limitExceeded = false;

        while (!queue.isEmpty()) {
            budget.check();
            if (states.size() > maxStates) {
                limitExceeded = true;
                break;
            }
            StateKey stateKey = queue.removeFirst();
            int[] state = states.get(stateKey);
            List<Step> steps = new ArrayList<Step>();
            for (int transitionIndex = 0; transitionIndex < transitions.size(); transitionIndex++) {
                budget.check();
                if (!topology.enabled(transitionIndex, state)) continue;
                Transition transition = transitions.get(transitionIndex);
                fired.add(transition);
                int[] next = topology.fire(transitionIndex, state);
                if (exceedsTokenLimit(next, budget)) {
                    limitExceeded = true;
                    continue;
                }
                StateKey nextKey = new StateKey(next);
                budget.reserve(96L);
                steps.add(new Step(nextKey, !transition.isInvisible()));
                if (!states.containsKey(nextKey)) {
                    if (states.size() >= maxStates) throw new Inconclusive();
                    states.put(nextKey, next);
                    budget.states = states.size();
                    queue.add(nextKey);
                }
            }
            graph.put(stateKey, steps);
        }

        if (limitExceeded) {
            return new Result(Collections.<String>emptyList(), multipleComponents, true, states.size());
        }

        if (!states.containsKey(finalKey)) defects.add("FINAL_NOT_REACHABLE");
        Map<StateKey, List<StateKey>> predecessors = new HashMap<StateKey, List<StateKey>>();
        for (StateKey key : states.keySet()) { budget.check(); predecessors.put(key, new ArrayList<StateKey>()); }
        for (Map.Entry<StateKey, List<Step>> entry : graph.entrySet()) {
            budget.check();
            for (Step step : entry.getValue()) { budget.reserve(8L); predecessors.get(step.target).add(entry.getKey()); }
        }
        Set<StateKey> canReachFinal = new HashSet<StateKey>();
        if (states.containsKey(finalKey)) {
            ArrayDeque<StateKey> reverseQueue = new ArrayDeque<StateKey>();
            canReachFinal.add(finalKey);
            reverseQueue.add(finalKey);
            while (!reverseQueue.isEmpty()) {
                budget.check();
                for (StateKey predecessor : predecessors.get(reverseQueue.removeFirst())) {
                    budget.check();
                    if (canReachFinal.add(predecessor)) reverseQueue.add(predecessor);
                }
            }
        }
        if (canReachFinal.size() != states.size()) defects.add("NO_OPTION_TO_COMPLETE");
        boolean visibleCompletion = false;
        for (List<Step> steps : graph.values()) {
            budget.check();
            for (Step step : steps) {
                budget.check();
                if (step.visible && canReachFinal.contains(step.target)) visibleCompletion = true;
            }
        }
        if (!visibleCompletion) defects.add("NO_NONTRIVIAL_COMPLETION");
        for (Transition transition : transitions) {
            budget.check();
            if (!fired.contains(transition)) {
                defects.add(transition.isInvisible() ? "DEAD_INVISIBLE_TRANSITION" : "DEAD_VISIBLE_TRANSITION");
            }
        }
        return new Result(new ArrayList<String>(defects), multipleComponents, false, states.size());
    }

    private int[] markingVector(Marking marking, List<Place> places, Map<Place, Integer> placeIndex, Budget budget) {
        if (marking == null) throw new IllegalArgumentException("Final marking is required");
        int[] tokens = new int[places.size()];
        for (Place place : marking.baseSet()) {
            budget.check();
            Integer index = placeIndex.get(place);
            if (index == null) throw new IllegalArgumentException("Marking contains a foreign place");
            tokens[index.intValue()] = marking.occurrences(place).intValue();
        }
        return tokens;
    }

    private boolean exceedsTokenLimit(int[] tokens, Budget budget) {
        for (int count : tokens) { budget.check(); if (count > maxTokensPerPlace || count < 0) return true; }
        return false;
    }

    private static boolean hasMultipleComponents(Petrinet net, List<Place> places, List<Transition> transitions, Budget budget) {
        Set<PetrinetNode> all = new HashSet<PetrinetNode>();
        all.addAll(places);
        all.addAll(transitions);
        if (all.isEmpty()) return false;
        Set<PetrinetNode> visited = new HashSet<PetrinetNode>();
        ArrayDeque<PetrinetNode> queue = new ArrayDeque<PetrinetNode>();
        queue.add(all.iterator().next());
        while (!queue.isEmpty()) {
            budget.check();
            PetrinetNode node = queue.removeFirst();
            if (!visited.add(node)) continue;
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(node)) {
                budget.check();
                queue.add(edge.getSource());
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(node)) {
                budget.check();
                queue.add(edge.getTarget());
            }
        }
        return visited.size() != all.size();
    }
}
