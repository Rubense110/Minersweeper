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
import java.io.StringReader;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
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
    public void ownPnmlWriterPreservesSpecialLabelsWeightsAndAllMarkings() throws Exception {
        String label = "á & \"B\" <活动> &amp; 'fin'";
        Petrinet net = PetrinetFactory.newPetrinet(label);
        Place start = net.addPlace(label), end = net.addPlace(label);
        Transition visible = net.addTransition(label), duplicate = net.addTransition(label);
        Transition hidden = net.addTransition("invisible & \"route\"");
        hidden.setInvisible(true);
        net.addArc(start, visible, 2); net.addArc(visible, end, 3);
        net.addArc(start, hidden); net.addArc(hidden, end);
        Marking initial = new Marking(); initial.add(start, 2);
        Marking fin = new Marking(); fin.add(end, 3);
        Marking alternative = new Marking(); alternative.add(start, 4); alternative.add(end, 5);
        List<Marking> finals = Arrays.asList(fin, alternative, new Marking());
        PmnlExporter exporter = new PmnlExporter();
        String pnml = exporter.exportPnml(null, net, initial, finals);
        assertEquals(pnml, exporter.exportPnml(null, net, initial, finals));
        Document document = DocumentBuilderFactory.newInstance().newDocumentBuilder()
            .parse(new InputSource(new StringReader(pnml)));
        XPath xpath = XPathFactory.newInstance().newXPath();
        String startId = exportedIdFor(pnml, "place", start.getLocalID().toString());
        String endId = exportedIdFor(pnml, "place", end.getLocalID().toString());
        String visibleId = exportedIdFor(pnml, "transition", visible.getLocalID().toString());
        assertEquals(label, xpath.evaluate("/pnml/net/name/text", document));
        assertEquals(label, xpath.evaluate("//transition[@id='" + visibleId + "']/name/text", document));
        assertEquals(label, xpath.evaluate("//transition[@id='" + visibleId + "']/toolspecific/@activity", document));
        assertEquals("2", xpath.evaluate("//place[@id='" + startId + "']/initialMarking/text", document));
        assertEquals("3", xpath.evaluate("/pnml/net/finalmarkings/marking[1]/place[@idref='" + endId + "']/text", document));
        assertEquals("4", xpath.evaluate("/pnml/net/finalmarkings/marking[2]/place[@idref='" + startId + "']/text", document));
        assertEquals("5", xpath.evaluate("/pnml/net/finalmarkings/marking[2]/place[@idref='" + endId + "']/text", document));
        assertEquals("0", xpath.evaluate("count(/pnml/net/finalmarkings/marking[3]/place)", document));
        assertEquals("2", xpath.evaluate("//arc[@source='" + startId + "' and @target='" + visibleId + "']/inscription/text", document));
        assertEquals("3", xpath.evaluate("//arc[@source='" + visibleId + "' and @target='" + endId + "']/inscription/text", document));
        PetriNetSemanticsSerializer.SerializedSemantics semantics = new PetriNetSemanticsSerializer()
            .serializeAll(net, pnml, initial, finals);
        assertEquals(3, semantics.transitions.size());
        assertEquals(3, semantics.finals.size());
        assertEquals(2, tokensFor(semantics.initial, startId));
        assertEquals(5, tokensFor(semantics.finals.get(1), endId));
        assertTrue(semantics.finals.get(2).isEmpty());
        assertTrue(invisibleFor(semantics.transitions, hidden.getLabel()));
        assertFalse(invisibleFor(semantics.transitions, label));
        assertFalse(visibleId.equals(exportedIdFor(pnml, "transition", duplicate.getLocalID().toString())));
        assertEquals(label, visible.getLabel());
    }

    @Test
    public void combinedSerializationPreservesUnicodeAndExactSemanticIds() throws Exception {
        Petrinet net = PetrinetFactory.newPetrinet("facturación clínica");
        Place start = net.addPlace("entrada"), end = net.addPlace("salida");
        Transition activity = net.addTransition("Revisión 日本語");
        net.addArc(start, activity); net.addArc(activity, end);
        Marking initial = new Marking(); initial.add(start, 2);
        Marking fin = new Marking(); fin.add(end, 3);
        try (com.minersweeper.javaservice.evaluation.ManagedCLIContext context = new com.minersweeper.javaservice.evaluation.ManagedCLIContext()) {
            String pnml = new PmnlExporter().exportPnml(context.plugin(), net);
            PetriNetSemanticsSerializer serializer = new PetriNetSemanticsSerializer();
            PetriNetSemanticsSerializer.SerializedSemantics combined = serializer.serializeAll(net, pnml, initial, Arrays.asList(fin));
            assertEquals(2, tokensFor(combined.initial, exportedIdFor(pnml, "place", start.getLocalID().toString())));
            assertEquals(3, tokensFor(combined.finals.get(0), exportedIdFor(pnml, "place", end.getLocalID().toString())));
            assertEquals("Revisión 日本語", combined.transitions.get(0).label);
            assertTrue(pnml.contains("encoding=\"UTF-8\""));
        }
    }

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
