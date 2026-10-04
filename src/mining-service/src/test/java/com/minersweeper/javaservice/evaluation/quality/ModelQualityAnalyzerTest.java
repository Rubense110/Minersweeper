package com.minersweeper.javaservice.evaluation.quality;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

public class ModelQualityAnalyzerTest {
    private final ModelQualityAnalyzer analyzer = new ModelQualityAnalyzer();

    @Test
    public void zeroDeadlineKeepsLogicalWorkBoundAndExternalCancellation() {
        com.minersweeper.javaservice.evaluation.quality.ReachabilitySupport.Budget budget =
            new com.minersweeper.javaservice.evaluation.quality.ReachabilitySupport.Budget(0L);
        for (int i = 0; i < 4_000_000; i++) budget.check();
        try { budget.check(); org.junit.Assert.fail("Logical budget must remain bounded"); }
        catch (com.minersweeper.javaservice.evaluation.quality.ReachabilitySupport.Inconclusive expected) { }
        Thread.currentThread().interrupt();
        try {
            new com.minersweeper.javaservice.evaluation.quality.ReachabilitySupport.Budget(0L).check();
            org.junit.Assert.fail("Cancellation must still interrupt analysis");
        } catch (java.util.concurrent.CancellationException expected) { }
        finally { Thread.interrupted(); }
    }

    @Test
    public void acceptsLinearModelWithoutChangingItsNet() {
        Petrinet net = PetrinetFactory.newPetrinet("linear");
        Place start = net.addPlace("start");
        Place end = net.addPlace("end");
        Transition activity = net.addTransition("A");
        net.addArc(start, activity);
        net.addArc(activity, end);
        int arcs = net.getEdges().size();
        ModelQualityAnalyzer.Result result = analyzer.analyze(net, marked(start), Arrays.asList(marked(end)));
        assertTrue(result.defects.toString(), result.defects.isEmpty());
        assertFalse(result.multipleComponents);
        assertFalse(result.inconclusive);
        assertTrue(result.violations().isEmpty());
        assertEquals(arcs, net.getEdges().size());
    }

    @Test
    public void rejectsTwoReachableAlternativeFinalsAsPolicyNotAsDeadCode() {
        Petrinet net = PetrinetFactory.newPetrinet("choice");
        Place start = net.addPlace("start");
        Place left = net.addPlace("left");
        Place right = net.addPlace("right");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        net.addArc(start, a);
        net.addArc(start, b);
        net.addArc(a, left);
        net.addArc(b, right);
        ModelQualityAnalyzer.Result result = analyzer.analyze(net, marked(start), Arrays.asList(marked(left), marked(right)));
        assertEquals(Arrays.asList("MULTIPLE_FINAL_MARKINGS"), result.defects);
        assertFalse(result.multipleComponents);
    }

    @Test
    public void rejectsConnectedJoinThatCannotFire() {
        Petrinet net = PetrinetFactory.newPetrinet("join");
        Place start = net.addPlace("start");
        Place missing = net.addPlace("missing");
        Place end = net.addPlace("end");
        Transition a = net.addTransition("A");
        net.addArc(start, a);
        net.addArc(missing, a);
        net.addArc(a, end);
        ModelQualityAnalyzer.Result result = analyzer.analyze(net, marked(start), Arrays.asList(marked(end)));
        assertTrue(result.defects.toString(), result.defects.contains("FINAL_NOT_REACHABLE"));
        assertTrue(result.defects.toString(), result.defects.contains("NO_NONTRIVIAL_COMPLETION"));
        assertTrue(result.defects.toString(), result.defects.contains("DEAD_VISIBLE_TRANSITION"));
        assertFalse(result.multipleComponents);
    }

    @Test
    public void emptyInitialAndFinalDoNotPassMerelyByMatching() {
        Petrinet net = PetrinetFactory.newPetrinet("empty");
        Place start = net.addPlace("start");
        Place end = net.addPlace("end");
        Transition a = net.addTransition("A");
        net.addArc(start, a);
        net.addArc(a, end);
        ModelQualityAnalyzer.Result result = analyzer.analyze(net, new Marking(), Arrays.asList(new Marking()));
        assertTrue(result.defects.toString(), result.defects.contains("NO_NONTRIVIAL_COMPLETION"));
        assertTrue(result.defects.toString(), result.defects.contains("DEAD_VISIBLE_TRANSITION"));
    }

    @Test
    public void reportsIndependentButCompletableComponentsSeparately() {
        Petrinet net = PetrinetFactory.newPetrinet("parallel");
        Place aStart = net.addPlace("aStart");
        Place aEnd = net.addPlace("aEnd");
        Place bStart = net.addPlace("bStart");
        Place bEnd = net.addPlace("bEnd");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        net.addArc(aStart, a);
        net.addArc(a, aEnd);
        net.addArc(bStart, b);
        net.addArc(b, bEnd);
        ModelQualityAnalyzer.Result result = analyzer.analyze(
            net, marked(aStart, bStart), Arrays.asList(marked(aEnd, bEnd))
        );
        assertTrue(result.defects.toString(), result.defects.isEmpty());
        assertTrue(result.multipleComponents);
        assertEquals(Arrays.asList("MULTIPLE_COMPONENTS"), result.violations());
    }

    @Test
    public void reportsUnboundedSearchAsInconclusiveNotValid() {
        Petrinet net = PetrinetFactory.newPetrinet("unbounded");
        Place start = net.addPlace("start");
        Place end = net.addPlace("end");
        Transition a = net.addTransition("A");
        Transition spawn = net.addTransition("spawn");
        net.addArc(start, a);
        net.addArc(a, end);
        net.addArc(spawn, start);
        ModelQualityAnalyzer.Result result = new ModelQualityAnalyzer(100, 2, 1_000_000_000L).analyze(
            net, marked(start), Collections.singletonList(marked(end))
        );
        assertTrue(result.inconclusive);
        assertTrue(result.violations().contains("QUALITY_CHECK_INCONCLUSIVE"));
    }

    private static Marking marked(Place... places) {
        Marking marking = new Marking();
        for (Place place : places) marking.add(place);
        return marking;
    }
}
