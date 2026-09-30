package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.util.Arrays;
import java.util.Iterator;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;

public class TokenReplayEngine {
    private static final int MAX_HIDDEN_RECURSION_DEPTH = 2;
    private static final int MAX_FINAL_MARKING_ITERATIONS = 5;

    private final Petrinet net;
    private final Marking initialMarking;
    private final Marking finalMarking;
    private final XEventClassifier classifier;
    private final TransEvClassMapping mapping;

    private Map<String, List<Transition>> visibleTransitionsByActivity;
    private Map<Transition, String> activityByVisibleTransition;
    private final CompiledReplayNet compiled;
    private final Map<Place, Map<Place, HiddenPathNode>> hiddenTrees =
        new LinkedHashMap<Place, Map<Place, HiddenPathNode>>(16, 0.75f, true);
    private long hiddenTreeBytes;
    private long enabledCacheBytes;
    private static final long MAX_CACHE_BYTES = 4L * 1024L * 1024L;
    private Map<MarkingKey, Set<String>> enabledActivityCache;

    public TokenReplayEngine(
        Petrinet net,
        Marking initialMarking,
        Marking finalMarking,
        XEventClassifier classifier,
        TransEvClassMapping mapping
    ) {
        this(net, initialMarking, finalMarking, classifier, mapping, new CompiledReplayNet(net));
    }

    public TokenReplayEngine(Petrinet net, Marking initialMarking, Marking finalMarking,
        XEventClassifier classifier, TransEvClassMapping mapping, CompiledReplayNet compiled) {
        this.compiled = compiled;
        this.net = net;
        this.initialMarking = initialMarking == null ? new Marking() : initialMarking;
        this.finalMarking = finalMarking == null ? new Marking() : finalMarking;
        this.classifier = classifier;
        this.mapping = mapping;
        this.enabledActivityCache = new LinkedHashMap<MarkingKey, Set<String>>(16, 0.75f, true);
    }

    public LogReplayStatistics statistics(XLog log) {
        return LogReplayStatistics.forLog(log, classifier);
    }

    public Map<List<String>, Integer> variantsByActivitySequence(XLog log) {
        return statistics(log).variants();
    }

    public Marking initialPrefixMarking() { return copyMarking(initialMarking); }

    public TraceReplay advancePrefix(Marking parent, String activity) {
        return replayActivitiesFrom(Collections.singletonList(activity), ReplayOptions.precisionPrefix(), parent);
    }

    public List<String> activitiesOf(XTrace trace) {
        List<String> activities = new ArrayList<String>();
        for (XEvent event : trace) {
            ExecutionChecks.check();
            String activity = classifier.getClassIdentity(event);
            if (activity != null) {
                activities.add(activity);
            }
        }
        return activities;
    }

    public TraceReplay replayFitnessTrace(List<String> activities) {
        ReplayOptions options = ReplayOptions.fitness();
        TraceReplay traceReplay = replayActivities(activities, options);

        HiddenReplay finalReplay = reachFinalMarkingThroughHidden(traceReplay.marking);
        Marking marking = finalReplay.marking;
        Counts counts = traceReplay.counts.copy();
        Map<Transition, Integer> activations = new LinkedHashMap<Transition, Integer>(traceReplay.activations);
        counts.add(finalReplay.counts, 1);
        mergeActivations(activations, finalReplay.activations, 1);

        long finalMissing = missingFinalTokens(marking);
        counts.missing += finalMissing;
        counts.consumed += tokenCount(finalMarking);
        long remaining = remainingTokens(marking);
        counts.remaining += remaining;

        boolean fit = traceReplay.fit && counts.missing == 0L && counts.remaining == 0L;
        return new TraceReplay(marking, counts, activations, fit);
    }

    public TraceReplay replayPrefix(List<String> activities) {
        return replayActivities(activities, ReplayOptions.precisionPrefix());
    }

    public Set<String> visibleActivitiesEventuallyEnabled(Marking sourceMarking) {
        MarkingKey key = new MarkingKey(sourceMarking, compiled);
        Set<String> cached = enabledActivityCache.get(key);
        if (cached != null) {
            return cached;
        }

        Set<String> activities = new LinkedHashSet<String>();
        for (Transition transition : compiled.transitions) {
            ExecutionChecks.check();
            if (transition.isInvisible()) {
                continue;
            }
            if (isEnabled(transition, sourceMarking)) {
                activities.add(activityOfVisibleTransition(transition));
                continue;
            }
            HiddenReplay hiddenReplay = applyHiddenTransitions(transition, sourceMarking);
            if (isEnabled(transition, hiddenReplay.marking)) {
                activities.add(activityOfVisibleTransition(transition));
            }
        }
        Set<String> immutable = Collections.unmodifiableSet(activities);
        long bytes = key.estimatedBytes() + 96L + 48L * immutable.size();
        if (bytes <= MAX_CACHE_BYTES) {
            while (!enabledActivityCache.isEmpty() && enabledCacheBytes + bytes > MAX_CACHE_BYTES) {
                ExecutionChecks.check();
                Iterator<Map.Entry<MarkingKey, Set<String>>> it = enabledActivityCache.entrySet().iterator();
                Map.Entry<MarkingKey, Set<String>> oldest = it.next();
                enabledCacheBytes -= oldest.getKey().estimatedBytes() + 96L + 48L * oldest.getValue().size();
                it.remove();
            }
            enabledActivityCache.put(key, immutable);
            enabledCacheBytes += bytes;
        }
        return immutable;
    }

    public Petrinet getNet() {
        return net;
    }

    private TraceReplay replayActivities(List<String> activities, ReplayOptions options) {
        return replayActivitiesFrom(activities, options, initialMarking);
    }

    private TraceReplay replayActivitiesFrom(List<String> activities, ReplayOptions options, Marking start) {
        ExecutionChecks.check();
        Marking marking = copyMarking(start);
        Counts counts = new Counts();
        if (options.countInitialTokens) {
            counts.produced += tokenCount(initialMarking);
        }
        Map<Transition, Integer> activations = new LinkedHashMap<Transition, Integer>();
        boolean fit = true;

        for (String activity : activities) {
            ExecutionChecks.check();
            List<Transition> candidates = transitionsForActivity(activity);
            if (candidates.isEmpty()) {
                counts.missing += 1L;
                fit = false;
                if (options.stopImmediatelyUnfit) {
                    return new TraceReplay(marking, counts, activations, false);
                }
                continue;
            }

            Transition transition = chooseTransition(candidates, marking);
            if (!isEnabled(transition, marking) && options.walkThroughHiddenTransitions) {
                HiddenReplay hiddenReplay = applyHiddenTransitions(transition, marking);
                marking = hiddenReplay.marking;
                counts.add(hiddenReplay.counts, 1);
                mergeActivations(activations, hiddenReplay.activations, 1);
            }

            if (!isEnabled(transition, marking)) {
                fit = false;
                if (options.stopImmediatelyUnfit) {
                    return new TraceReplay(marking, counts, activations, false);
                }
                counts.missing += addMissingTokens(transition, marking);
            }

            fire(transition, marking, counts, activations);
        }

        return new TraceReplay(marking, counts, activations, fit);
    }

    private Transition chooseTransition(List<Transition> candidates, Marking marking) {
        for (Transition candidate : candidates) {
            ExecutionChecks.check();
            if (isEnabled(candidate, marking)) {
                return candidate;
            }
        }
        Transition best = candidates.get(0);
        int bestDistance = Integer.MAX_VALUE;
        for (Transition candidate : candidates) {
            ExecutionChecks.check();
            int distance = hiddenDistanceToEnable(candidate, marking);
            if (distance < bestDistance) {
                best = candidate;
                bestDistance = distance;
            }
        }
        return best;
    }

    private HiddenReplay applyHiddenTransitions(Transition target, Marking sourceMarking) {
        return applyHiddenTransitions(target, sourceMarking, new LinkedHashSet<Transition>(), 0);
    }

    private HiddenReplay applyHiddenTransitions(
        Transition target,
        Marking sourceMarking,
        Set<Transition> visitedTransitions,
        int recursionDepth
    ) {
        Marking marking = copyMarking(sourceMarking);
        Counts counts = new Counts();
        Map<Transition, Integer> activations = new LinkedHashMap<Transition, Integer>();
        if (recursionDepth >= MAX_HIDDEN_RECURSION_DEPTH || visitedTransitions.contains(target)) {
            return new HiddenReplay(marking, counts, activations);
        }
        visitedTransitions.add(target);

        boolean changed;
        do {
            changed = false;
            List<List<Transition>> paths = hiddenPathsToMissingPlaces(target, marking);
            for (List<Transition> path : paths) {
                ExecutionChecks.check();
                for (Transition hidden : path) {
                    ExecutionChecks.check();
                    if (hidden == target || visitedTransitions.contains(hidden)) {
                        continue;
                    }
                    if (!isEnabled(hidden, marking)) {
                        HiddenReplay nested = applyHiddenTransitions(
                            hidden,
                            marking,
                            visitedTransitions,
                            recursionDepth + 1
                        );
                        marking = nested.marking;
                        counts.add(nested.counts, 1);
                        mergeActivations(activations, nested.activations, 1);
                    }
                    if (isEnabled(hidden, marking)) {
                        fire(hidden, marking, counts, activations);
                        visitedTransitions.add(hidden);
                        changed = true;
                    }
                    if (isEnabled(target, marking)) {
                        return new HiddenReplay(marking, counts, activations);
                    }
                }
            }
        } while (changed && !isEnabled(target, marking));

        return new HiddenReplay(marking, counts, activations);
    }

    private HiddenReplay reachFinalMarkingThroughHidden(Marking sourceMarking) {
        Marking marking = copyMarking(sourceMarking);
        Counts counts = new Counts();
        Map<Transition, Integer> activations = new LinkedHashMap<Transition, Integer>();

        for (int iteration = 0; iteration < MAX_FINAL_MARKING_ITERATIONS && !hasFinalTokens(marking); iteration++) {
            ExecutionChecks.check();
            boolean changed = false;
            List<List<Transition>> paths = hiddenPathsToFinalMarking(marking);
            for (List<Transition> path : paths) {
                ExecutionChecks.check();
                for (Transition hidden : path) {
                    ExecutionChecks.check();
                    if (isEnabled(hidden, marking)) {
                        fire(hidden, marking, counts, activations);
                        changed = true;
                    } else {
                        break;
                    }
                    if (hasFinalTokens(marking)) {
                        return new HiddenReplay(marking, counts, activations);
                    }
                }
            }
            if (!changed) {
                break;
            }
        }

        return new HiddenReplay(marking, counts, activations);
    }

    private List<List<Transition>> hiddenPathsToMissingPlaces(Transition target, Marking marking) {
        List<List<Transition>> paths = new ArrayList<List<Transition>>();
        Collection<Place> markedPlaces = marking.baseSet();
        List<Place> missingPlaces = missingInputPlaces(target, marking);

        for (Place from : sortedPlaces(markedPlaces)) {
            ExecutionChecks.check();
            Map<Place, HiddenPathNode> fromPaths = hiddenPathsFrom(from);
            for (Place to : sortedPlaces(missingPlaces)) {
                ExecutionChecks.check();
                List<Transition> path = materializePath(fromPaths.get(to));
                if (path != null && !path.isEmpty()) {
                    paths.add(path);
                }
            }
        }
        Collections.sort(paths, new TransitionPathComparator());
        return paths;
    }

    private List<List<Transition>> hiddenPathsToFinalMarking(Marking marking) {
        List<List<Transition>> paths = new ArrayList<List<Transition>>();
        for (Place from : sortedPlaces(marking.baseSet())) {
            ExecutionChecks.check();
            Map<Place, HiddenPathNode> fromPaths = hiddenPathsFrom(from);
            for (Place to : sortedPlaces(finalMarking.baseSet())) {
                ExecutionChecks.check();
                List<Transition> path = materializePath(fromPaths.get(to));
                if (path != null && !path.isEmpty()) {
                    paths.add(path);
                }
            }
        }
        Collections.sort(paths, new TransitionPathComparator());
        return paths;
    }

    private int hiddenDistanceToEnable(Transition transition, Marking marking) {
        if (isEnabled(transition, marking)) {
            return 0;
        }
        int best = Integer.MAX_VALUE;
        for (List<Transition> path : hiddenPathsToMissingPlaces(transition, marking)) {
            ExecutionChecks.check();
            best = Math.min(best, path.size());
        }
        return best;
    }

    private Map<Place, HiddenPathNode> hiddenPathsFrom(Place source) {
        Map<Place, HiddenPathNode> cached = hiddenTrees.get(source);
        if (cached != null) return cached;
        Map<Place, HiddenPathNode> paths = new LinkedHashMap<Place, HiddenPathNode>();
        ArrayDeque<HiddenPathNode> queue = new ArrayDeque<HiddenPathNode>();
        Set<Place> visited = new HashSet<Place>();
        queue.add(new HiddenPathNode(source, null, null));
        visited.add(source);
        while (!queue.isEmpty()) {
            ExecutionChecks.check();
            HiddenPathNode state = queue.removeFirst();
            for (Transition hidden : compiled.hiddenSuccessors.get(state.place)) {
                ExecutionChecks.check();
                for (Place target : compiled.targets.get(hidden)) {
                    ExecutionChecks.check();
                    if (!visited.add(target)) continue;
                    HiddenPathNode next = new HiddenPathNode(target, state, hidden);
                    paths.put(target, next);
                    queue.addLast(next);
                }
            }
        }
        long bytes = 128L + 112L * paths.size();
        if (bytes <= MAX_CACHE_BYTES) {
            while (!hiddenTrees.isEmpty() && hiddenTreeBytes + bytes > MAX_CACHE_BYTES) {
                ExecutionChecks.check();
                Iterator<Map<Place, HiddenPathNode>> it = hiddenTrees.values().iterator();
                hiddenTreeBytes -= 128L + 112L * it.next().size(); it.remove();
            }
            hiddenTrees.put(source, paths); hiddenTreeBytes += bytes;
        }
        return paths;
    }

    private List<Transition> materializePath(HiddenPathNode node) {
        if (node == null) return null;
        List<Transition> path = new ArrayList<Transition>(node.depth);
        for (HiddenPathNode current = node; current.transition != null; current = current.parent) {
            ExecutionChecks.check(); path.add(current.transition);
        }
        Collections.reverse(path);
        return path;
    }

    private boolean isEnabled(Transition transition, Marking marking) {
        for (Arc arc : inputArcs(transition)) {
            ExecutionChecks.check();
            Place place = (Place) arc.getSource();
            if (marking.occurrences(place).intValue() < arc.getWeight()) {
                return false;
            }
        }
        return true;
    }

    private long addMissingTokens(Transition transition, Marking marking) {
        long missing = 0L;
        for (Arc arc : inputArcs(transition)) {
            ExecutionChecks.check();
            Place place = (Place) arc.getSource();
            int available = marking.occurrences(place).intValue();
            int needed = arc.getWeight();
            if (available < needed) {
                int delta = needed - available;
                marking.add(place, Integer.valueOf(delta));
                missing += delta;
            }
        }
        return missing;
    }

    private void fire(
        Transition transition,
        Marking marking,
        Counts counts,
        Map<Transition, Integer> activations
    ) {
        long consumed = consumedTokens(transition);
        long produced = producedTokens(transition);
        for (Arc arc : inputArcs(transition)) {
            ExecutionChecks.check();
            marking.add((Place) arc.getSource(), Integer.valueOf(-arc.getWeight()));
        }
        for (Arc arc : outputArcs(transition)) {
            ExecutionChecks.check();
            marking.add((Place) arc.getTarget(), Integer.valueOf(arc.getWeight()));
        }
        counts.consumed += consumed;
        counts.produced += produced;
        addActivation(activations, transition, 1);
    }

    private long consumedTokens(Transition transition) {
        long consumed = 0L;
        for (Arc arc : inputArcs(transition)) {
            ExecutionChecks.check();
            consumed += arc.getWeight();
        }
        return consumed;
    }

    private long producedTokens(Transition transition) {
        long produced = 0L;
        for (Arc arc : outputArcs(transition)) {
            ExecutionChecks.check();
            produced += arc.getWeight();
        }
        return produced;
    }

    private List<Arc> inputArcs(Transition transition) { return compiled.inputs.get(transition); }
    private List<Arc> outputArcs(Transition transition) { return compiled.outputs.get(transition); }

    private List<Place> missingInputPlaces(Transition transition, Marking marking) {
        List<Place> places = new ArrayList<Place>();
        for (Arc arc : inputArcs(transition)) {
            ExecutionChecks.check();
            Place place = (Place) arc.getSource();
            if (marking.occurrences(place).intValue() < arc.getWeight()) {
                places.add(place);
            }
        }
        return places;
    }

    private long missingFinalTokens(Marking marking) {
        long missing = 0L;
        for (Place place : finalMarking.baseSet()) {
            ExecutionChecks.check();
            int current = marking.occurrences(place).intValue();
            int expected = finalMarking.occurrences(place).intValue();
            if (current < expected) {
                missing += expected - current;
            }
        }
        return missing;
    }

    private long remainingTokens(Marking marking) {
        long remaining = 0L;
        for (Place place : marking.baseSet()) {
            ExecutionChecks.check();
            int current = marking.occurrences(place).intValue();
            int expected = finalMarking.occurrences(place).intValue();
            if (current > expected) {
                remaining += current - expected;
            }
        }
        return remaining;
    }

    private boolean hasFinalTokens(Marking marking) {
        for (Place place : finalMarking.baseSet()) {
            ExecutionChecks.check();
            if (marking.occurrences(place).intValue() < finalMarking.occurrences(place).intValue()) {
                return false;
            }
        }
        return true;
    }

    private long tokenCount(Marking marking) {
        if (marking == null) {
            return 0L;
        }
        long count = 0L;
        for (Place place : marking.baseSet()) {
            ExecutionChecks.check();
            count += marking.occurrences(place).intValue();
        }
        return count;
    }

    private List<Transition> transitionsForActivity(String activity) {
        List<Transition> transitions = visibleTransitionsByActivity().get(activity);
        return transitions == null ? Collections.<Transition>emptyList() : transitions;
    }

    private Map<String, List<Transition>> visibleTransitionsByActivity() {
        if (visibleTransitionsByActivity != null) {
            return visibleTransitionsByActivity;
        }
        visibleTransitionsByActivity = new LinkedHashMap<String, List<Transition>>();
        activityByVisibleTransition = new LinkedHashMap<Transition, String>();
        for (Transition transition : compiled.transitions) {
            ExecutionChecks.check();
            if (transition.isInvisible()) {
                continue;
            }
            String activity = resolveActivity(transition);
            addTransitionForActivity(activity, transition);
            activityByVisibleTransition.put(transition, activity);
            if (activity.endsWith("+complete")) {
                addTransitionForActivity(activity.substring(0, activity.length() - "+complete".length()), transition);
            }
        }
        return visibleTransitionsByActivity;
    }

    private String activityOfVisibleTransition(Transition transition) {
        visibleTransitionsByActivity();
        String activity = activityByVisibleTransition.get(transition);
        return activity == null ? resolveActivity(transition) : activity;
    }

    private String resolveActivity(Transition transition) {
        XEventClass eventClass = mapping.get(transition);
        String activity = eventClass == null ? transition.getLabel() : eventClass.getId();
        if (activity == null || "DUMMY".equals(activity)) {
            activity = transition.getLabel();
        }
        return activity;
    }

    private void addTransitionForActivity(String activity, Transition transition) {
        List<Transition> transitions = visibleTransitionsByActivity.get(activity);
        if (transitions == null) {
            transitions = new ArrayList<Transition>();
            visibleTransitionsByActivity.put(activity, transitions);
        }
        transitions.add(transition);
    }

    private Marking copyMarking(Marking source) {
        Marking copy = new Marking();
        if (source != null) {
            copy.addAll(source);
        }
        return copy;
    }

    private List<Place> sortedPlaces(Collection<Place> places) {
        List<Place> sorted = new ArrayList<Place>(places);
        Collections.sort(sorted);
        return sorted;
    }

    private List<Transition> sortedTransitions(Collection<Transition> transitions) {
        List<Transition> sorted = new ArrayList<Transition>(transitions);
        Collections.sort(sorted);
        return sorted;
    }

    private void mergeActivations(
        Map<Transition, Integer> target,
        Map<Transition, Integer> source,
        int multiplicity
    ) {
        for (Map.Entry<Transition, Integer> entry : source.entrySet()) {
            ExecutionChecks.check();
            addActivation(target, entry.getKey(), entry.getValue().intValue() * multiplicity);
        }
    }

    public static void addActivation(Map<Transition, Integer> activations, Transition transition, int amount) {
        Integer current = activations.get(transition);
        activations.put(transition, Integer.valueOf((current == null ? 0 : current.intValue()) + amount));
    }

    public static class Counts {
        long missing;
        long consumed;
        long remaining;
        long produced;

        void add(Counts other, int multiplicity) {
            missing += other.missing * multiplicity;
            consumed += other.consumed * multiplicity;
            remaining += other.remaining * multiplicity;
            produced += other.produced * multiplicity;
        }

        Counts copy() {
            Counts copy = new Counts();
            copy.missing = missing;
            copy.consumed = consumed;
            copy.remaining = remaining;
            copy.produced = produced;
            return copy;
        }
    }

    public static class TraceReplay {
        final Marking marking;
        final Counts counts;
        final Map<Transition, Integer> activations;
        final boolean fit;

        TraceReplay(Marking marking, Counts counts, Map<Transition, Integer> activations, boolean fit) {
            this.marking = marking;
            this.counts = counts;
            this.activations = activations;
            this.fit = fit;
        }

        public Marking marking() {
            return marking;
        }

        public Counts counts() {
            return counts;
        }

        public Map<Transition, Integer> activations() {
            return activations;
        }

        public boolean fit() {
            return fit;
        }
    }

    private static class HiddenReplay {
        final Marking marking;
        final Counts counts;
        final Map<Transition, Integer> activations;

        HiddenReplay(Marking marking, Counts counts, Map<Transition, Integer> activations) {
            this.marking = marking;
            this.counts = counts;
            this.activations = activations;
        }
    }

    private static class HiddenPathNode {
        final Place place;
        final HiddenPathNode parent;
        final Transition transition;
        final int depth;
        HiddenPathNode(Place place, HiddenPathNode parent, Transition transition) {
            this.place = place; this.parent = parent; this.transition = transition;
            depth = parent == null ? 0 : parent.depth + 1;
        }
    }

    private static class ReplayOptions {
        final boolean countInitialTokens;
        final boolean walkThroughHiddenTransitions;
        final boolean stopImmediatelyUnfit;

        ReplayOptions(
            boolean countInitialTokens,
            boolean walkThroughHiddenTransitions,
            boolean stopImmediatelyUnfit
        ) {
            this.countInitialTokens = countInitialTokens;
            this.walkThroughHiddenTransitions = walkThroughHiddenTransitions;
            this.stopImmediatelyUnfit = stopImmediatelyUnfit;
        }

        static ReplayOptions fitness() {
            return new ReplayOptions(true, true, false);
        }

        static ReplayOptions precisionPrefix() {
            return new ReplayOptions(false, true, true);
        }
    }

    private static class MarkingKey {
        private final long[] tokens;
        private final int hash;
        MarkingKey(Marking marking, CompiledReplayNet compiled) {
            tokens = new long[marking.baseSet().size()];
            int index = 0;
            for (Place place : marking.baseSet()) {
                ExecutionChecks.check();
                tokens[index++] = (((long) compiled.placeIndexes.get(place).intValue()) << 32)
                    | (marking.occurrences(place).intValue() & 0xffffffffL);
            }
            Arrays.sort(tokens); hash = Arrays.hashCode(tokens);
        }
        long estimatedBytes() { return 48L + 8L * tokens.length; }
        @Override public boolean equals(Object other) {
            return other instanceof MarkingKey && Arrays.equals(tokens, ((MarkingKey) other).tokens);
        }
        @Override public int hashCode() { return hash; }
    }

    private static class TransitionPathComparator implements java.util.Comparator<List<Transition>> {
        public int compare(List<Transition> left, List<Transition> right) {
            int sizeComparison = left.size() - right.size();
            if (sizeComparison != 0) {
                return sizeComparison;
            }
            return pathKey(left).compareTo(pathKey(right));
        }

        private static String pathKey(List<Transition> path) {
            StringBuilder builder = new StringBuilder();
            for (Transition transition : path) {
                ExecutionChecks.check();
                if (builder.length() > 0) {
                    builder.append('|');
                }
                builder.append(transition.getLabel());
            }
            return builder.toString();
        }
    }
}
