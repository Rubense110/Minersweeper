package com.minersweeper.javaservice.evaluation.discovery.miners;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.HashSet;
import java.util.Set;
import org.deckfour.xes.extension.std.XConceptExtension;
import org.deckfour.xes.factory.XFactoryNaiveImpl;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;
import com.minersweeper.javaservice.evaluation.ExecutionChecks;

public class HeuristicsFinalMarkingPolicyTest {
    @Test
    public void prefixBudgetIsIndependentOfColdOrWarmLogStatistics() {
        Petrinet net = PetrinetFactory.newPetrinet("cycle with repeated traces");
        Place start = net.addPlace("start"); Place afterA = net.addPlace("afterA");
        Transition a = net.addTransition("A"); Transition b = net.addTransition("B");
        net.addArc(start, a); net.addArc(a, afterA); net.addArc(afterA, b); net.addArc(b, start);
        Marking initial = new Marking(); initial.add(start);
        String[][] traces = new String[2000][];
        for (int i = 0; i < traces.length; i++) traces[i] = new String[] {"A"};
        XLog log = log(traces);
        HeuristicsFinalMarkingPolicy policy = new HeuristicsFinalMarkingPolicy(1000L);
        for (int i = 0; i < 2; i++) {
            HeuristicsFinalMarkingPolicy.Result result = policy.choose(net, initial, log);
            assertEquals("replayed_prefix_fallback", result.source);
            assertEquals(1, result.finalMarkings.get(0).occurrences(afterA).intValue());
            assertEquals(0, result.finalMarkings.get(0).occurrences(start).intValue());
        }
    }

    @Test
    public void exhaustedPrefixWorkUsesTheSameReachableInitialMarkingColdAndWarm() {
        Petrinet net = PetrinetFactory.newPetrinet("bounded cycle");
        Place start = net.addPlace("start"); Place afterA = net.addPlace("afterA");
        Transition a = net.addTransition("A"); Transition b = net.addTransition("B");
        net.addArc(start, a); net.addArc(a, afterA); net.addArc(afterA, b); net.addArc(b, start);
        Marking initial = new Marking(); initial.add(start);
        XLog log = log(new String[] {"A"});
        HeuristicsFinalMarkingPolicy policy = new HeuristicsFinalMarkingPolicy(1L);
        for (int i = 0; i < 2; i++) assertEquals(initial, policy.choose(net, initial, log).finalMarkings.get(0));
        ExecutionChecks.check();
    }

    @Test
    public void safetyTimeCutoffNeverReturnsAnAlternativeAcceptingMarking() {
        Petrinet net = PetrinetFactory.newPetrinet("time cutoff");
        Place start = net.addPlace("start");
        Marking initial = new Marking(); initial.add(start);
        try (ExecutionChecks.Deadline deadline = ExecutionChecks.within(1L)) {
            new HeuristicsFinalMarkingPolicy().choose(net, initial, log(new String[] {"A"}));
            org.junit.Assert.fail("The timeout must escape the policy");
        } catch (ExecutionChecks.DeadlineExceeded expected) {
            assertEquals("REPRODUCIBILITY_TIME_LIMIT", expected.code);
        }
    }

    @Test
    public void keepsBothReachableAlternativeFinalsWithoutChangingNet() {
        Petrinet net = PetrinetFactory.newPetrinet("choice");
        Place start = net.addPlace("start");
        Place branch = net.addPlace("branch");
        Place endB = net.addPlace("endB");
        Place endC = net.addPlace("endC");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        Transition c = net.addTransition("C");
        net.addArc(start, a);
        net.addArc(a, branch);
        net.addArc(branch, b);
        net.addArc(branch, c);
        net.addArc(b, endB);
        net.addArc(c, endC);
        int edges = net.getEdges().size();
        Marking initial = new Marking();
        initial.add(start);

        HeuristicsFinalMarkingPolicy.Result result = new HeuristicsFinalMarkingPolicy().choose(
            net, initial, log(new String[] {"A", "B"}, new String[] {"A", "C"})
        );

        assertEquals("reachable_terminal", result.source);
        assertEquals(2, result.finalMarkings.size());
        Set<Place> ends = new HashSet<Place>();
        for (Marking fin : result.finalMarkings) {
            assertEquals(1, fin.size());
            ends.addAll(fin.baseSet());
        }
        assertTrue(ends.contains(endB));
        assertTrue(ends.contains(endC));
        assertEquals(4, net.getPlaces().size());
        assertEquals(3, net.getTransitions().size());
        assertEquals(edges, net.getEdges().size());
    }

    @Test
    public void fallsBackToReachableReplayedPrefixWhenNoTerminalExists() {
        Petrinet net = PetrinetFactory.newPetrinet("cycle");
        Place start = net.addPlace("start");
        Place afterA = net.addPlace("afterA");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        net.addArc(start, a);
        net.addArc(a, afterA);
        net.addArc(afterA, b);
        net.addArc(b, start);
        Marking initial = new Marking();
        initial.add(start);

        HeuristicsFinalMarkingPolicy.Result result = new HeuristicsFinalMarkingPolicy().choose(
            net, initial, log(new String[] {"A"})
        );

        assertEquals("replayed_prefix_fallback", result.source);
        assertEquals(1, result.finalMarkings.size());
        assertEquals(1, result.finalMarkings.get(0).occurrences(afterA).intValue());
        assertEquals(0, result.finalMarkings.get(0).occurrences(start).intValue());
        assertEquals(4, net.getEdges().size());
    }

    private static XLog log(String[]... traces) {
        XFactoryNaiveImpl factory = new XFactoryNaiveImpl();
        XLog log = factory.createLog();
        for (String[] activities : traces) {
            XTrace trace = factory.createTrace();
            for (String activity : activities) {
                XEvent event = factory.createEvent();
                XConceptExtension.instance().assignName(event, activity);
                trace.add(event);
            }
            log.add(trace);
        }
        return log;
    }
}
