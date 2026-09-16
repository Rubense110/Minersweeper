import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import com.minersweeper.javaservice.evaluation.serialization.PetriNetSemanticsSerializer;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.Test;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

public class PetriNetSemanticsSerializerTest {

    @Test
    public void serializesExactMarkingsAndTransitionInvisibility() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("semantic-net");
        Place p0 = net.addPlace("p0");
        Place p1 = net.addPlace("p1");
        Transition visibleTau = net.addTransition("tau");
        Transition hiddenNamed = net.addTransition("internal routing");
        hiddenNamed.setInvisible(true);

        Marking initial = new Marking();
        initial.add(p0, 3);
        initial.add(p1, 2);
        Marking finalMarking = new Marking();
        finalMarking.add(p1, 4);

        PetriNetSemanticsSerializer serializer = new PetriNetSemanticsSerializer();
        String pnml = new PmnlExporter().exportPnml(new CLIPluginContext(new CLIContext(), "semantic-test"), net);
        List<ArtifactBulkResponse.MarkingEntry> initialPayload = serializer.serializeMarking(net, pnml, initial);
        List<ArtifactBulkResponse.MarkingEntry> finalPayload = serializer.serializeMarking(net, pnml, finalMarking);
        List<List<ArtifactBulkResponse.MarkingEntry>> finals = serializer.serializeFinalMarkings(
            net, pnml, Arrays.asList(finalMarking, new Marking())
        );
        List<ArtifactBulkResponse.TransitionEntry> transitions = serializer.serializeTransitions(net, pnml);
        String p0ExportedId = exportedIdFor(pnml, "place", p0.getLocalID().toString());
        String p1ExportedId = exportedIdFor(pnml, "place", p1.getLocalID().toString());

        assertEquals(2, initialPayload.size());
        assertEquals(3, tokensFor(initialPayload, p0ExportedId));
        assertEquals(2, tokensFor(initialPayload, p1ExportedId));
        assertEquals(1, finalPayload.size());
        assertEquals(4, tokensFor(finalPayload, p1ExportedId));
        assertEquals(2, finals.size());
        assertTrue(finals.get(1).isEmpty());
        assertTrue(pnml.contains("id=\"" + initialPayload.get(0).place_id + "\""));
        assertTrue(pnml.contains("id=\"" + initialPayload.get(1).place_id + "\""));
        assertTrue(invisibleFor(transitions, "internal routing"));
        assertFalse(invisibleFor(transitions, "tau"));
        assertEquals(1, serializer.countVisibleTransitions(net));
    }

    @Test
    public void countsOnlySemanticallyVisibleTransitions() {
        PetriNetSemanticsSerializer serializer = new PetriNetSemanticsSerializer();
        Petrinet noTransitions = PetrinetFactory.newPetrinet("none");
        Petrinet invisibleOnly = PetrinetFactory.newPetrinet("invisible-only");
        Transition hidden = invisibleOnly.addTransition("ordinary label");
        hidden.setInvisible(true);
        Petrinet visibleTau = PetrinetFactory.newPetrinet("visible-tau");
        visibleTau.addTransition("tau");

        assertEquals(0, serializer.countVisibleTransitions(noTransitions));
        assertEquals(0, serializer.countVisibleTransitions(invisibleOnly));
        assertEquals(1, serializer.countVisibleTransitions(visibleTau));
    }

    private static int tokensFor(List<ArtifactBulkResponse.MarkingEntry> marking, String placeId) {
        for (ArtifactBulkResponse.MarkingEntry entry : marking) {
            if (placeId.equals(entry.place_id)) {
                return entry.tokens;
            }
        }
        return 0;
    }

    private static boolean invisibleFor(List<ArtifactBulkResponse.TransitionEntry> transitions, String label) {
        for (ArtifactBulkResponse.TransitionEntry transition : transitions) {
            if (label.equals(transition.label)) {
                return transition.invisible;
            }
        }
        throw new AssertionError("transition not found: " + label);
    }

    private static String exportedIdFor(String pnml, String element, String localNodeId) {
        Pattern pattern = Pattern.compile(
            "<" + element + " id=\\\"([^\\\"]+)\\\"(?:(?!<" + element + ").)*?<toolspecific[^>]*localNodeID=\\\""
                + Pattern.quote(localNodeId) + "\\\"",
            Pattern.DOTALL
        );
        Matcher matcher = pattern.matcher(pnml);
        if (!matcher.find()) {
            throw new AssertionError("exported node not found");
        }
        return matcher.group(1);
    }
}
