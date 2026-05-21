import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.ControlFlowComplexity;
import com.minersweeper.javaservice.evaluation.conformance.metrics.EdgeCount;
import com.minersweeper.javaservice.evaluation.conformance.metrics.EdgeLoadCentrality;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;

import static org.junit.Assert.assertEquals;

public class ConformanceStructuralMetricsTest {
    @Test
    public void edgeCountReturnsNumberOfPetriNetArcs() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("edge-count");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Place p1 = net.addPlace("p1");
        net.addArc(p0, t0);
        net.addArc(t0, p1);

        assertEquals(2.0, new EdgeCount().compute(computation(net)), 0.0);
    }

    @Test
    public void controlFlowComplexityUsesPlacesAsXorAndTransitionsAsAndSplits() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("cfc");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Transition t1 = net.addTransition("t1");
        Place p1 = net.addPlace("p1");
        Place p2 = net.addPlace("p2");
        net.addArc(p0, t0);
        net.addArc(p0, t1);
        net.addArc(t0, p1);
        net.addArc(t0, p2);

        assertEquals(3.0, new ControlFlowComplexity().compute(computation(net)), 0.0);
    }

    @Test
    public void edgeLoadCentralityAveragesRawDirectedEdgeBetweennessScores() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("elc");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Place p1 = net.addPlace("p1");
        net.addArc(p0, t0);
        net.addArc(t0, p1);

        assertEquals(2.0, new EdgeLoadCentrality().compute(computation(net)), 0.0);
    }

    @Test
    public void edgeLoadCentralityDividesTiedShortestPathsAcrossEdges() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("elc-tie");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Transition t1 = net.addTransition("t1");
        Place p1 = net.addPlace("p1");
        net.addArc(p0, t0);
        net.addArc(p0, t1);
        net.addArc(t0, p1);
        net.addArc(t1, p1);

        assertEquals(1.5, new EdgeLoadCentrality().compute(computation(net)), 0.0);
    }

    private static ConformanceComputation computation(Petrinet net) {
        return new ConformanceComputation(null, null, net, null, null, null, null);
    }
}
