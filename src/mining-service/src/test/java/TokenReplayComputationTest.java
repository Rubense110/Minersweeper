import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMode;
import com.minersweeper.javaservice.evaluation.conformance.TokenReplayResult;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.extension.std.XConceptExtension;
import org.deckfour.xes.factory.XFactory;
import org.deckfour.xes.factory.XFactoryRegistry;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

public class TokenReplayComputationTest {
    @Test
    public void tokenReplayReturnsPerfectFitnessForMatchingTrace() throws Exception {
        Model model = sequenceModel();

        TokenReplayResult result = computation(log("A", "B"), model).getTokenReplayResult();

        assertEquals(1.0, result.fitness(), 0.0);
        assertEquals(0L, result.missing());
        assertEquals(0L, result.remaining());
        assertEquals(1L, result.fitTraceCount());
    }

    @Test
    public void tokenReplayWalksThroughInvisibleTransitionsToEnableVisibleTransition() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("hidden");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Place p2 = net.addPlace("p2");
        Transition tau = net.addTransition("tau");
        tau.setInvisible(true);
        Transition visible = net.addTransition("A");
        net.addArc(p0, tau);
        net.addArc(tau, p1);
        net.addArc(p1, visible);
        net.addArc(visible, p2);

        Marking initial = new Marking();
        initial.add(p0);
        Marking fin = new Marking();
        fin.add(p2);

        TokenReplayResult result = computation(log("A"), new Model(net, initial, fin)).getTokenReplayResult();

        assertEquals(1.0, result.fitness(), 0.0);
        assertEquals(0L, result.missing());
        assertEquals(0L, result.remaining());
        assertEquals(2, result.transitionActivations().size());
    }

    @Test
    public void tokenReplayCountsMissingAndRemainingTokensForUnfitTrace() throws Exception {
        Model model = sequenceModel();

        TokenReplayResult result = computation(log("B"), model).getTokenReplayResult();

        assertTrue(result.fitness() < 1.0);
        assertTrue(result.missing() > 0L);
        assertTrue(result.remaining() > 0L);
        assertEquals(0L, result.fitTraceCount());
    }

    @Test
    public void tokenReplayGeneralisationUsesTokenReplayActivations() throws Exception {
        Model model = sequenceModel();

        double generalisation = computation(log("A", "B"), model).getGeneralisation();

        assertEquals(0.0, generalisation, 0.0);
    }

    @Test
    public void tokenReplayPrecisionIsPerfectForExactSequenceModel() throws Exception {
        Model model = sequenceModel();

        double precision = computation(log("A", "B"), model).getPrecision();

        assertEquals(1.0, precision, 0.0);
    }

    @Test
    public void tokenReplayPrecisionPenalizesEscapingEdges() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("extra-branch");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Place p2 = net.addPlace("p2");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        Transition c = net.addTransition("C");
        net.addArc(p0, a);
        net.addArc(a, p1);
        net.addArc(p1, b);
        net.addArc(b, p2);
        net.addArc(p1, c);
        net.addArc(c, p2);

        Marking initial = new Marking();
        initial.add(p0);
        Marking fin = new Marking();
        fin.add(p2);

        double precision = computation(log("A", "B"), new Model(net, initial, fin)).getPrecision();

        assertEquals(2.0 / 3.0, precision, 0.000001);
    }

    @Test
    public void tokenReplayPrecisionConsidersVisibleTransitionsReachableThroughInvisibleTransitions() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("hidden-extra-branch");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Place p2 = net.addPlace("p2");
        Transition tau = net.addTransition("tau");
        tau.setInvisible(true);
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        net.addArc(p0, tau);
        net.addArc(tau, p1);
        net.addArc(p1, a);
        net.addArc(a, p2);
        net.addArc(p1, b);
        net.addArc(b, p2);

        Marking initial = new Marking();
        initial.add(p0);
        Marking fin = new Marking();
        fin.add(p2);

        double precision = computation(log("A"), new Model(net, initial, fin)).getPrecision();

        assertEquals(0.5, precision, 0.000001);
    }

    private static ConformanceComputation computation(XLog log, Model model) {
        return new ConformanceComputation(
            null,
            log,
            model.net,
            model.initial,
            model.fin,
            ConformanceMode.REPLAY_TOKEN,
            null
        );
    }

    private static Model sequenceModel() {
        Petrinet net = PetrinetFactory.newPetrinet("sequence");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Place p2 = net.addPlace("p2");
        Transition a = net.addTransition("A");
        Transition b = net.addTransition("B");
        net.addArc(p0, a);
        net.addArc(a, p1);
        net.addArc(p1, b);
        net.addArc(b, p2);

        Marking initial = new Marking();
        initial.add(p0);
        Marking fin = new Marking();
        fin.add(p2);
        return new Model(net, initial, fin);
    }

    private static XLog log(String... activities) {
        XFactory factory = XFactoryRegistry.instance().currentDefault();
        XLog log = factory.createLog();
        log.getClassifiers().add(new XEventNameClassifier());
        XTrace trace = factory.createTrace();
        XConceptExtension.instance().assignName(trace, "case-1");
        for (String activity : activities) {
            XEvent event = factory.createEvent();
            XConceptExtension.instance().assignName(event, activity);
            trace.add(event);
        }
        log.add(trace);
        return log;
    }

    private static class Model {
        final Petrinet net;
        final Marking initial;
        final Marking fin;

        Model(Petrinet net, Marking initial, Marking fin) {
            this.net = net;
            this.initial = initial;
            this.fin = fin;
        }
    }
}
