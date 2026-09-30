package com.minersweeper.javaservice.evaluation.quality;

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
        final String target;
        final boolean visible;

        Step(String target, boolean visible) {
            this.target = target;
            this.visible = visible;
        }
    }

    public Result analyze(Petrinet net, Marking initial, List<Marking> finals) {
        if (net == null || initial == null || finals == null) {
            throw new IllegalArgumentException("Net and markings are required");
        }

        List<Place> places = new ArrayList<Place>(net.getPlaces());
        List<Transition> transitions = new ArrayList<Transition>(net.getTransitions());
        Map<Place, Integer> placeIndex = new HashMap<Place, Integer>();
        for (int index = 0; index < places.size(); index++) {
            placeIndex.put(places.get(index), Integer.valueOf(index));
        }
        boolean multipleComponents = hasMultipleComponents(net, places, transitions);
        LinkedHashSet<String> defects = new LinkedHashSet<String>();
        int visibleCount = 0;
        for (Transition transition : transitions) if (!transition.isInvisible()) visibleCount++;
        if (visibleCount == 0) defects.add("NO_VISIBLE_TRANSITIONS");
        if (finals.size() != 1) defects.add("MULTIPLE_FINAL_MARKINGS");
        if (!defects.isEmpty()) return new Result(new ArrayList<String>(defects), multipleComponents, false, 0);

        int[] start = markingVector(initial, places, placeIndex);
        int[] fin = markingVector(finals.get(0), places, placeIndex);
        if (exceedsTokenLimit(start) || exceedsTokenLimit(fin)) {
            return new Result(Collections.<String>emptyList(), multipleComponents, true, 0);
        }
        int[][] consume = new int[transitions.size()][places.size()];
        int[][] produce = new int[transitions.size()][places.size()];
        for (int index = 0; index < transitions.size(); index++) {
            Transition transition = transitions.get(index);
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(transition)) {
                if (!(edge instanceof Arc) || !(edge.getSource() instanceof Place)) {
                    return new Result(Collections.<String>emptyList(), multipleComponents, true, 0);
                }
                consume[index][placeIndex.get((Place) edge.getSource()).intValue()] += ((Arc) edge).getWeight();
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(transition)) {
                if (!(edge instanceof Arc) || !(edge.getTarget() instanceof Place)) {
                    return new Result(Collections.<String>emptyList(), multipleComponents, true, 0);
                }
                produce[index][placeIndex.get((Place) edge.getTarget()).intValue()] += ((Arc) edge).getWeight();
            }
        }

        String startKey = Arrays.toString(start);
        String finalKey = Arrays.toString(fin);
        Map<String, int[]> states = new LinkedHashMap<String, int[]>();
        Map<String, List<Step>> graph = new LinkedHashMap<String, List<Step>>();
        ArrayDeque<String> queue = new ArrayDeque<String>();
        states.put(startKey, start);
        queue.add(startKey);
        Set<Transition> fired = new HashSet<Transition>();
        long deadline = System.nanoTime() + maxNanos;
        boolean limitExceeded = false;

        while (!queue.isEmpty()) {
            if (states.size() > maxStates || System.nanoTime() > deadline) {
                limitExceeded = true;
                break;
            }
            String stateKey = queue.removeFirst();
            int[] state = states.get(stateKey);
            List<Step> steps = new ArrayList<Step>();
            for (int transitionIndex = 0; transitionIndex < transitions.size(); transitionIndex++) {
                boolean enabled = true;
                for (int placeIndexValue = 0; placeIndexValue < places.size(); placeIndexValue++) {
                    if (state[placeIndexValue] < consume[transitionIndex][placeIndexValue]) {
                        enabled = false;
                        break;
                    }
                }
                if (!enabled) continue;
                Transition transition = transitions.get(transitionIndex);
                fired.add(transition);
                int[] next = new int[places.size()];
                for (int placeIndexValue = 0; placeIndexValue < places.size(); placeIndexValue++) {
                    next[placeIndexValue] = state[placeIndexValue]
                        - consume[transitionIndex][placeIndexValue] + produce[transitionIndex][placeIndexValue];
                }
                if (exceedsTokenLimit(next)) {
                    limitExceeded = true;
                    continue;
                }
                String nextKey = Arrays.toString(next);
                steps.add(new Step(nextKey, !transition.isInvisible()));
                if (!states.containsKey(nextKey)) {
                    states.put(nextKey, next);
                    queue.add(nextKey);
                }
            }
            graph.put(stateKey, steps);
        }

        if (limitExceeded) {
            return new Result(Collections.<String>emptyList(), multipleComponents, true, states.size());
        }

        if (!states.containsKey(finalKey)) defects.add("FINAL_NOT_REACHABLE");
        Map<String, List<String>> predecessors = new HashMap<String, List<String>>();
        for (String key : states.keySet()) predecessors.put(key, new ArrayList<String>());
        for (Map.Entry<String, List<Step>> entry : graph.entrySet()) {
            for (Step step : entry.getValue()) predecessors.get(step.target).add(entry.getKey());
        }
        Set<String> canReachFinal = new HashSet<String>();
        if (states.containsKey(finalKey)) {
            ArrayDeque<String> reverseQueue = new ArrayDeque<String>();
            canReachFinal.add(finalKey);
            reverseQueue.add(finalKey);
            while (!reverseQueue.isEmpty()) {
                for (String predecessor : predecessors.get(reverseQueue.removeFirst())) {
                    if (canReachFinal.add(predecessor)) reverseQueue.add(predecessor);
                }
            }
        }
        if (canReachFinal.size() != states.size()) defects.add("NO_OPTION_TO_COMPLETE");
        boolean visibleCompletion = false;
        for (List<Step> steps : graph.values()) {
            for (Step step : steps) {
                if (step.visible && canReachFinal.contains(step.target)) visibleCompletion = true;
            }
        }
        if (!visibleCompletion) defects.add("NO_NONTRIVIAL_COMPLETION");
        for (Transition transition : transitions) {
            if (!fired.contains(transition)) {
                defects.add(transition.isInvisible() ? "DEAD_INVISIBLE_TRANSITION" : "DEAD_VISIBLE_TRANSITION");
            }
        }
        return new Result(new ArrayList<String>(defects), multipleComponents, false, states.size());
    }

    private int[] markingVector(Marking marking, List<Place> places, Map<Place, Integer> placeIndex) {
        if (marking == null) throw new IllegalArgumentException("Final marking is required");
        int[] tokens = new int[places.size()];
        for (Place place : marking.baseSet()) {
            Integer index = placeIndex.get(place);
            if (index == null) throw new IllegalArgumentException("Marking contains a foreign place");
            tokens[index.intValue()] = marking.occurrences(place).intValue();
        }
        return tokens;
    }

    private boolean exceedsTokenLimit(int[] tokens) {
        for (int count : tokens) if (count > maxTokensPerPlace || count < 0) return true;
        return false;
    }

    private static boolean hasMultipleComponents(Petrinet net, List<Place> places, List<Transition> transitions) {
        Set<PetrinetNode> all = new HashSet<PetrinetNode>();
        all.addAll(places);
        all.addAll(transitions);
        if (all.isEmpty()) return false;
        Set<PetrinetNode> visited = new HashSet<PetrinetNode>();
        ArrayDeque<PetrinetNode> queue = new ArrayDeque<PetrinetNode>();
        queue.add(all.iterator().next());
        while (!queue.isEmpty()) {
            PetrinetNode node = queue.removeFirst();
            if (!visited.add(node)) continue;
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(node)) {
                queue.add(edge.getSource());
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(node)) {
                queue.add(edge.getTarget());
            }
        }
        return visited.size() != all.size();
    }
}
