import static org.junit.Assert.*;
import com.minersweeper.javaservice.evaluation.conformance.*;
import java.util.*;
import java.util.concurrent.*;
import org.deckfour.xes.classification.*;
import org.deckfour.xes.extension.std.XConceptExtension;
import org.deckfour.xes.factory.*;
import org.deckfour.xes.model.*;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.*;
import org.processmining.models.graphbased.directed.petrinet.elements.*;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;

public class TokenReplayPerformanceTest {
    @Test public void incrementalPrecisionMatchesIndependentWholePrefixOracle() {
        Petrinet net = PetrinetFactory.newPetrinet("branch-hidden-weighted-loop");
        Place start = net.addPlace("start"), middle = net.addPlace("middle"), end = net.addPlace("end");
        Transition tau = net.addTransition("tau"); tau.setInvisible(true);
        Transition a = net.addTransition("A"), b = net.addTransition("B"), c = net.addTransition("C");
        net.addArc(start, tau, 2); net.addArc(tau, middle, 2);
        net.addArc(middle, a, 2); net.addArc(a, middle, 2);
        net.addArc(middle, b, 2); net.addArc(b, end, 2);
        net.addArc(middle, c, 2); net.addArc(c, end, 2);
        Marking initial = new Marking(); initial.add(start, 2);
        Marking fin = new Marking(); fin.add(end, 2);
        Random random = new Random(42);
        for (int trial = 0; trial < 20; trial++) {
            XLog log = factory().createLog();
            log.add(trace()); log.add(trace("A", "B")); log.add(trace("A", "B"));
            for (int t = 0; t < 8; t++) {
                String[] sequence = new String[random.nextInt(8)];
                for (int i = 0; i < sequence.length; i++) sequence[i] = new String[]{"A", "B", "C", "unknown"}[random.nextInt(4)];
                log.add(trace(sequence));
            }
            TokenReplayPrecisionResult expected = naivePrecision(log, engine(net, initial, fin));
            TokenReplayPrecisionResult actual = new TokenReplayPrecisionComputation(log, engine(net, initial, fin), null).compute();
            assertEquals(expected.prefixCount(), actual.prefixCount());
            assertEquals(expected.replayedPrefixCount(), actual.replayedPrefixCount());
            assertEquals(expected.activatedTransitions(), actual.activatedTransitions());
            assertEquals(expected.escapingEdges(), actual.escapingEdges());
            assertEquals(expected.precision(), actual.precision(), 0.0);
        }
    }

    @Test public void longRepeatedTraceReplaysOneEdgePerDistinctPrefix() {
        Petrinet net = PetrinetFactory.newPetrinet("loop"); Place p = net.addPlace("p");
        Transition a = net.addTransition("A"); net.addArc(p, a); net.addArc(a, p);
        Marking marking = new Marking(); marking.add(p);
        XLog log = factory().createLog(); String[] sequence = new String[4000]; Arrays.fill(sequence, "A");
        log.add(trace(sequence)); log.add(trace(sequence));
        final int[] steps = {0};
        TokenReplayEngine replay = new TokenReplayEngine(net, marking, marking, new XEventNameClassifier(), mapping(net)) {
            @Override public TraceReplay advancePrefix(Marking parent, String activity) {
                steps[0]++; return super.advancePrefix(parent, activity);
            }
        };
        TokenReplayPrecisionResult result = new TokenReplayPrecisionComputation(log, replay, null).compute();
        assertEquals(4000, steps[0]); assertEquals(4001, replay.statistics(log).prefixNodeCount());
        assertEquals(8002L, result.prefixCount()); assertEquals(8002L, result.replayedPrefixCount());
        assertEquals(8002L, result.activatedTransitions()); assertEquals(2L, result.escapingEdges());
    }

    @Test public void cacheSharesStatisticsAndSeparatesClassifiers() {
        XLog log = factory().createLog(); log.add(trace("A", "B"));
        XEventClassifier name = new XEventNameClassifier();
        LogReplayStatistics first = LogReplayStatistics.forLog(log, name);
        assertSame(first, LogReplayStatistics.forLog(log, new XEventNameClassifier()));
        assertNotSame(first, LogReplayStatistics.forLog(log, new XEventAttributeClassifier("other", "concept:name", "lifecycle:transition")));
        LogReplayStatistics.evict(log);
        assertNotSame(first, LogReplayStatistics.forLog(log, name));
    }

    @Test public void interruptedReplayAndStatisticsStopWithoutClearingSignal() {
        Petrinet net = PetrinetFactory.newPetrinet("cancel"); Place p = net.addPlace("p");
        Marking marking = new Marking(); marking.add(p);
        Thread.currentThread().interrupt();
        try {
            try { engine(net, marking, marking).replayPrefix(Arrays.asList("A")); fail("expected cancellation"); }
            catch (CancellationException expected) { assertTrue(Thread.currentThread().isInterrupted()); }
            try { LogReplayStatistics.forLog(factory().createLog(), new XEventNameClassifier()); fail("expected cancellation"); }
            catch (CancellationException expected) { assertTrue(Thread.currentThread().isInterrupted()); }
        } finally { Thread.interrupted(); }
    }

    private static TokenReplayPrecisionResult naivePrecision(XLog log, TokenReplayEngine engine) {
        Map<List<String>, Long> frequencies = new LinkedHashMap<>();
        Map<List<String>, Set<String>> next = new HashMap<>();
        for (XTrace trace : log) {
            List<String> activities = engine.activitiesOf(trace);
            for (int length = 0; length <= activities.size(); length++) {
                List<String> prefix = new ArrayList<>(activities.subList(0, length));
                frequencies.put(prefix, frequencies.getOrDefault(prefix, 0L) + 1L);
                next.computeIfAbsent(prefix, key -> new HashSet<>());
                if (length < activities.size()) next.get(prefix).add(activities.get(length));
            }
        }
        long prefixes = 0, replayed = 0, activated = 0, escaping = 0;
        for (Map.Entry<List<String>, Long> entry : frequencies.entrySet()) {
            prefixes += entry.getValue();
            TokenReplayEngine.TraceReplay replay = engine.replayPrefix(entry.getKey());
            if (!replay.fit()) continue;
            replayed += entry.getValue();
            Set<String> enabled = engine.visibleActivitiesEventuallyEnabled(replay.marking());
            activated += enabled.size() * entry.getValue();
            for (String activity : enabled) if (!next.get(entry.getKey()).contains(activity)) escaping += entry.getValue();
        }
        return new TokenReplayPrecisionResult(prefixes, replayed, activated, escaping);
    }
    private static TokenReplayEngine engine(Petrinet net, Marking initial, Marking fin) {
        return new TokenReplayEngine(net, initial, fin, new XEventNameClassifier(), mapping(net));
    }
    private static TransEvClassMapping mapping(Petrinet net) {
        XEventClass dummy = new XEventClass("DUMMY", 0);
        return new TransEvClassMapping(new XEventNameClassifier(), dummy);
    }
    private static XFactory factory() { return XFactoryRegistry.instance().currentDefault(); }
    private static XTrace trace(String... activities) {
        XTrace trace = factory().createTrace();
        for (String activity : activities) { XEvent event = factory().createEvent(); XConceptExtension.instance().assignName(event, activity); trace.add(event); }
        return trace;
    }
}
