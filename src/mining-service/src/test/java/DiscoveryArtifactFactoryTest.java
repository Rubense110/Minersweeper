import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import java.util.LinkedHashSet;
import java.util.Set;
import org.junit.Test;
import org.processmining.acceptingpetrinet.models.impl.AcceptingPetriNetImpl;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

public class DiscoveryArtifactFactoryTest {

    @Test
    public void preservesEmptyInitialMarkingAndAllAcceptingFinalMarkings() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("accepting-net");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Marking initial = new Marking();
        Marking evaluatedFinal = new Marking();
        evaluatedFinal.add(p0, 2);
        Marking additionalFinal = new Marking();
        additionalFinal.add(p1, 3);
        Set<Marking> finals = new LinkedHashSet<Marking>();
        finals.add(evaluatedFinal);
        finals.add(additionalFinal);

        DiscoveryArtifactFactory factory = new DiscoveryArtifactFactory(new PmnlExporter() {
            @Override
            public String exportPnml(org.processmining.framework.plugin.PluginContext context, Petrinet exportedNet) {
                return "<pnml/>";
            }
        });
        DiscoveryArtifact artifact = factory.fromResultArray(
            null,
            new Object[] {new AcceptingPetriNetImpl(net, initial, finals)}
        );

        assertEquals(0, artifact.getInitialMarking().size());
        assertEquals(2, artifact.getFinalMarking().occurrences(p0).intValue());
        assertEquals(2, artifact.getFinalMarkings().size());
        assertEquals(3, artifact.getFinalMarkings().get(1).occurrences(p1).intValue());
    }

    @Test
    public void failsInsteadOfInventingMarkings() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("unmarked-net");
        net.addPlace("p0");
        DiscoveryArtifactFactory factory = new DiscoveryArtifactFactory(new PmnlExporter());
        try {
            factory.fromResultArray(null, new Object[] {net});
            fail("Expected a missing-semantic-marking failure");
        } catch (IllegalStateException expected) {
            assertEquals("Miner result has no accepting Petri-net semantics (initial/final marking)", expected.getMessage());
        }
    }

    @Test
    public void preservesExplicitEmptyMarkingsInsteadOfTreatingThemAsAbsent() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("explicit-empty-net");
        Place source = net.addPlace("source");
        net.addPlace("sink");
        DiscoveryArtifactFactory factory = new DiscoveryArtifactFactory(new PmnlExporter() {
            @Override
            public String exportPnml(org.processmining.framework.plugin.PluginContext context, Petrinet exportedNet) {
                return "<pnml/>";
            }
        });

        Marking additionalFinal = new Marking();
        additionalFinal.add(source, 2);
        DiscoveryArtifact artifact = factory.fromResultArray(
            null, new Object[] {net, new Marking(), new Marking(), additionalFinal}
        );

        assertEquals(0, artifact.getInitialMarking().size());
        assertEquals(0, artifact.getFinalMarking().size());
        assertEquals(2, artifact.getFinalMarkings().size());
        assertEquals(2, artifact.getFinalMarkings().get(1).occurrences(source).intValue());
    }
}
