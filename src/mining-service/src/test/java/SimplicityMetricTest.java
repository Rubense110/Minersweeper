import static org.junit.Assert.assertEquals;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Simplicity;
import org.junit.Test;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;

public class SimplicityMetricTest {
    @Test
    public void simplicityReturnsOneForSequentialModelWithMeanArcDegreeAtBaseline() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("simplicity-sequential");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Place p1 = net.addPlace("p1");
        net.addArc(p0, t0);
        net.addArc(t0, p1);

        assertEquals(1.0, new Simplicity().compute(computation(net)), 0.0);
    }

    @Test
    public void simplicityMatchesPm4pyArcDegreeFormulaWhenMeanArcDegreeExceedsBaseline() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("simplicity-branching");
        Place p0 = net.addPlace("p0");
        Transition t0 = net.addTransition("t0");
        Transition t1 = net.addTransition("t1");
        Transition t2 = net.addTransition("t2");
        Transition t3 = net.addTransition("t3");
        Place p1 = net.addPlace("p1");
        net.addArc(p0, t0);
        net.addArc(p0, t1);
        net.addArc(p0, t2);
        net.addArc(p0, t3);
        net.addArc(t0, p1);
        net.addArc(t1, p1);
        net.addArc(t2, p1);
        net.addArc(t3, p1);

        assertEquals(0.6, new Simplicity().compute(computation(net)), 1e-9);
    }

    private static ConformanceComputation computation(Petrinet net) {
        return new ConformanceComputation(null, null, net, null, null, null, null);
    }
}
