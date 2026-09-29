package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.evaluation.conformance.TokenReplayEngine;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfoFactory;
import org.deckfour.xes.model.XLog;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;

/** Assigns accepting semantics without changing the Petri net returned by ProM. */
final class HeuristicsFinalMarkingPolicy {
    private static final int MAX_STATES = 5000;
    private static final int MAX_TOKENS_PER_PLACE = 3;
    private static final long MAX_SEARCH_NANOS = 1_000_000_000L;

    static final class Result {
        final List<Marking> finalMarkings;
        final String source;

        Result(List<Marking> finalMarkings, String source) {
            this.finalMarkings = finalMarkings;
            this.source = source;
        }
    }

    Result choose(Petrinet net, Marking initial, XLog log) {
        SearchResult search = searchTerminalMarkings(net, initial);
        if (search.complete && !search.terminals.isEmpty()) {
            return new Result(search.terminals, "reachable_terminal");
        }
        Marking replayed = bestReachablePrefix(net, initial, log);
        return new Result(Collections.singletonList(replayed), "replayed_prefix_fallback");
    }

    private SearchResult searchTerminalMarkings(Petrinet net, Marking initial) {
        List<Place> places = new ArrayList<Place>(net.getPlaces());
        List<Transition> transitions = new ArrayList<Transition>(net.getTransitions());
        Map<Place, Integer> indexes = new LinkedHashMap<Place, Integer>();
        for (int i = 0; i < places.size(); i++) indexes.put(places.get(i), Integer.valueOf(i));
        int[] start = new int[places.size()];
        for (Place place : initial.baseSet()) {
            Integer index = indexes.get(place);
            if (index == null) return new SearchResult(false, Collections.<Marking>emptyList());
            start[index.intValue()] = initial.occurrences(place).intValue();
        }
        int[][] consume = new int[transitions.size()][places.size()];
        int[][] produce = new int[transitions.size()][places.size()];
        for (int i = 0; i < transitions.size(); i++) {
            Transition transition = transitions.get(i);
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(transition)) {
                if (!(edge instanceof Arc) || !(edge.getSource() instanceof Place))
                    return new SearchResult(false, Collections.<Marking>emptyList());
                consume[i][indexes.get((Place) edge.getSource()).intValue()] += ((Arc) edge).getWeight();
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(transition)) {
                if (!(edge instanceof Arc) || !(edge.getTarget() instanceof Place))
                    return new SearchResult(false, Collections.<Marking>emptyList());
                produce[i][indexes.get((Place) edge.getTarget()).intValue()] += ((Arc) edge).getWeight();
            }
        }
        boolean[] sink = new boolean[places.size()];
        for (int i = 0; i < places.size(); i++) sink[i] = net.getOutEdges(places.get(i)).isEmpty();

        ArrayDeque<int[]> queue = new ArrayDeque<int[]>();
        Map<String, int[]> seen = new LinkedHashMap<String, int[]>();
        queue.add(start);
        seen.put(Arrays.toString(start), start);
        List<Marking> terminals = new ArrayList<Marking>();
        long deadline = System.nanoTime() + MAX_SEARCH_NANOS;
        while (!queue.isEmpty()) {
            if (seen.size() > MAX_STATES || System.nanoTime() > deadline)
                return new SearchResult(false, Collections.<Marking>emptyList());
            int[] state = queue.removeFirst();
            boolean enabledAny = false;
            for (int transition = 0; transition < transitions.size(); transition++) {
                boolean enabled = true;
                for (int place = 0; place < places.size(); place++) {
                    if (state[place] < consume[transition][place]) { enabled = false; break; }
                }
                if (!enabled) continue;
                enabledAny = true;
                int[] next = new int[places.size()];
                boolean withinLimit = true;
                for (int place = 0; place < places.size(); place++) {
                    next[place] = state[place] - consume[transition][place] + produce[transition][place];
                    if (next[place] > MAX_TOKENS_PER_PLACE) withinLimit = false;
                }
                if (!withinLimit) return new SearchResult(false, Collections.<Marking>emptyList());
                String key = Arrays.toString(next);
                if (!seen.containsKey(key)) { seen.put(key, next); queue.add(next); }
            }
            if (!enabledAny && onlySinkTokens(state, sink)) terminals.add(toMarking(state, places));
        }
        Collections.sort(terminals, new Comparator<Marking>() {
            @Override public int compare(Marking left, Marking right) {
                return markingKey(left).compareTo(markingKey(right));
            }
        });
        return new SearchResult(true, terminals);
    }

    private boolean onlySinkTokens(int[] state, boolean[] sink) {
        for (int i = 0; i < state.length; i++) if (state[i] > 0 && !sink[i]) return false;
        return true;
    }

    private Marking toMarking(int[] state, List<Place> places) {
        Marking marking = new Marking();
        for (int i = 0; i < state.length; i++) if (state[i] > 0) marking.add(places.get(i), state[i]);
        return marking;
    }

    private Marking bestReachablePrefix(Petrinet net, Marking initial, XLog log) {
        if (log == null || log.isEmpty()) return copy(initial);
        XEventNameClassifier classifier = new XEventNameClassifier();
        XEventClasses classes = XLogInfoFactory.createLogInfo(log, classifier).getEventClasses();
        XEventClass dummy = new XEventClass("DUMMY", classes.size() + 1);
        TransEvClassMapping mapping = new TransEvClassMapping(classifier, dummy);
        for (Transition transition : net.getTransitions()) {
            XEventClass eventClass = classes.getByIdentity(transition.getLabel());
            if (eventClass == null) eventClass = classes.getByIdentity(transition.getLabel() + "+complete");
            mapping.put(transition, eventClass == null ? dummy : eventClass);
        }
        TokenReplayEngine engine = new TokenReplayEngine(net, initial, initial, classifier, mapping);
        Map<String, Candidate> candidates = new LinkedHashMap<String, Candidate>();
        long deadline = System.nanoTime() + MAX_SEARCH_NANOS;
        for (Map.Entry<List<String>, Integer> variant : engine.variantsByActivitySequence(log).entrySet()) {
            if (System.nanoTime() > deadline) break;
            TokenReplayEngine.TraceReplay replay = engine.replayPrefix(variant.getKey());
            Marking marking = replay.marking();
            String key = markingKey(marking);
            Candidate candidate = candidates.get(key);
            if (candidate == null) {
                candidate = new Candidate(copy(marking));
                candidates.put(key, candidate);
            }
            if (replay.fit()) candidate.completed += variant.getValue().intValue();
            candidate.frequency += variant.getValue().intValue();
        }
        Candidate best = null;
        for (Candidate candidate : candidates.values()) {
            if (best == null || candidate.completed > best.completed
                || (candidate.completed == best.completed && candidate.frequency > best.frequency)
                || (candidate.completed == best.completed && candidate.frequency == best.frequency
                    && markingKey(candidate.marking).compareTo(markingKey(best.marking)) < 0)) best = candidate;
        }
        return best == null ? copy(initial) : best.marking;
    }

    private static Marking copy(Marking original) {
        Marking copy = new Marking();
        for (Place place : original.baseSet()) copy.add(place, original.occurrences(place).intValue());
        return copy;
    }

    private static String markingKey(Marking marking) {
        List<String> parts = new ArrayList<String>();
        for (Place place : marking.baseSet()) {
            parts.add(place.getLabel() + ":" + place.getId() + ":" + marking.occurrences(place));
        }
        Collections.sort(parts);
        return parts.toString();
    }

    private static final class SearchResult {
        final boolean complete;
        final List<Marking> terminals;
        SearchResult(boolean complete, List<Marking> terminals) {
            this.complete = complete;
            this.terminals = terminals;
        }
    }

    private static final class Candidate {
        final Marking marking;
        int completed;
        int frequency;
        Candidate(Marking marking) { this.marking = marking; }
    }
}
