import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.miners.AlphaMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.xml.parsers.DocumentBuilderFactory;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;
import org.processmining.alphaminer.parameters.AlphaRobustMinerParameters;
import org.processmining.alphaminer.parameters.AlphaVersion;
import org.processmining.alphaminer.plugins.AlphaMinerPlugin;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public class PromPipelineEvaluatorRealTest {
    @Test
    public void ownPnmlRoundTripsThroughProMWithExactAcceptingSemantics() throws Exception {
        String label = "á & \"B\" <活动> &amp; 'fin'";
        Petrinet net = org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory.newPetrinet(label);
        Place start = net.addPlace(label), end = net.addPlace(label);
        Transition visible = net.addTransition(label), hidden = net.addTransition("route");
        hidden.setInvisible(true);
        net.addTransition("tau"); // A visible activity named tau must stay visible.
        net.addArc(start, visible, 2); net.addArc(visible, end, 3);
        net.addArc(start, hidden); net.addArc(hidden, end);
        org.processmining.models.semantics.petrinet.Marking initial = new org.processmining.models.semantics.petrinet.Marking();
        initial.add(start, 2);
        org.processmining.models.semantics.petrinet.Marking fin = new org.processmining.models.semantics.petrinet.Marking();
        fin.add(end, 3);
        List<org.processmining.models.semantics.petrinet.Marking> finals = Arrays.asList(fin,
            new org.processmining.models.semantics.petrinet.Marking());
        try (com.minersweeper.javaservice.evaluation.ManagedCLIContext context = new com.minersweeper.javaservice.evaluation.ManagedCLIContext()) {
            String pnml = new PmnlExporter().exportPnml(context.plugin(), net, initial, finals);
            byte[] bytes = pnml.getBytes(StandardCharsets.UTF_8);
            org.processmining.plugins.pnml.base.Pnml imported = new org.processmining.plugins.pnml.importing.PnmlImportUtils()
                .importPnmlFromStream(context.plugin(), new ByteArrayInputStream(bytes), "roundtrip.pnml", bytes.length);
            assertNotNull(imported);
            assertTrue(!imported.hasErrors());
            Petrinet restored = org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory.newPetrinet("restored");
            org.processmining.models.semantics.petrinet.Marking restoredInitial = new org.processmining.models.semantics.petrinet.Marking();
            List<org.processmining.models.semantics.petrinet.Marking> restoredFinals = new ArrayList<>();
            imported.convertToNet(restored, restoredInitial, restoredFinals,
                new org.processmining.models.connections.GraphLayoutConnection(restored));
            assertEquals(new com.minersweeper.javaservice.evaluation.reproducibility.CanonicalNetOrder(net, initial, finals).semanticHash(),
                new com.minersweeper.javaservice.evaluation.reproducibility.CanonicalNetOrder(restored, restoredInitial, restoredFinals).semanticHash());
        }
    }
    private static Path workDir;
    private static Path logFile;
    private static ArtifactStore store;
    private static PromPipelineEvaluator evaluator;

    @BeforeClass
    public static void setup() throws Exception {
        String runFlag = System.getenv("RUN_REAL_PROM_TESTS");
        Assume.assumeTrue(
            "Set RUN_REAL_PROM_TESTS=1 to run real ProM evaluator tests",
            "1".equals(runFlag)
        );

        Path promHome = resolvePromHome();
        Assume.assumeTrue("PROM_HOME not found: " + promHome, Files.isDirectory(promHome));

        Path lpsolveDir = findLpSolveNativeDir(promHome);
        Assume.assumeTrue("lpsolve native directory not found under: " + promHome, lpsolveDir != null);
        String nativePath = System.getProperty("java.library.path", "");
        if (!nativePath.contains(lpsolveDir.toAbsolutePath().toString())) {
            throw new IllegalStateException(
                "Run ./run_real_prom_tests.sh (or set LD_LIBRARY_PATH="
                + lpsolveDir.toAbsolutePath() + ") so the test JVM can load lpsolve"
            );
        }

        workDir = Files.createTempDirectory("prom-real-evaluator-test");
        logFile = TestFixtures.createTinyLog(workDir, "tiny-test-log.xes");

        store = new ArtifactStore(workDir.resolve("artifacts").toString());
        evaluator = new PromPipelineEvaluator(store, workDir);
    }

    @Test(timeout = 1200000)
    public void allActiveMinerVariantsProduceMetricsAndArtifacts() throws Exception {
        List<PipelineRequest.MinerConfig> miners = TestFixtures.activeMinerVariants();
        String selectedMiner = System.getenv("PROM_REAL_MINER");
        String selectedVariant = System.getenv("PROM_REAL_VARIANT");
        List<String> failures = new ArrayList<String>();
        int checked = 0;

        for (PipelineRequest.MinerConfig miner : miners) {
            if ((selectedMiner != null && !selectedMiner.equals(miner.key))
                || (selectedVariant != null && !selectedVariant.equals(miner.variant))) {
                continue;
            }
            checked++;
            try {
                String experimentId = "real_miner_" + checked;
                PipelineRequest request = TestFixtures.buildRequest(
                    experimentId,
                    logFile.toString(),
                    TestFixtures.matrixFilter(),
                    miner,
                    TestFixtures.defaultMetrics()
                );
                request.conformance_mode = "replay-token";

                EvaluationResult result = evaluator.evaluate(request);
                assertEquals(experimentId, result.experiment_id);
                assertNotNull(result.evaluation_id);
                assertTrue(result.fingerprint.contains(miner.key));
                assertEquals(Integer.valueOf(3), result.model_schema_version);
                assertEvaluationMetrics(result);

                ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
                assertEquals(1, bulk.artifacts.size());
                ArtifactBulkResponse.ArtifactEntry artifact = bulk.artifacts.get(0);
                assertEquals(miner.key, artifact.pipeline.miner.key);
                assertEquals(miner.variant, artifact.pipeline.miner.variant);
                assertTrue(artifact.pnml.contains("pnml"));
                assertV3Semantics(artifact);
                System.out.println("PASS " + miner.key + " / " + miner.variant);
            } catch (Exception | AssertionError error) {
                failures.add(miner.key + " / " + miner.variant + ": " + error);
                System.err.println("FAIL " + failures.get(failures.size() - 1));
            }
        }
        assertTrue("No miner variant matched PROM_REAL_MINER=" + selectedMiner
            + " and PROM_REAL_VARIANT=" + selectedVariant, checked > 0);
        if (!failures.isEmpty()) {
            fail("Real ProM variant failures:\n" + String.join("\n", failures));
        }
    }

    @Test(timeout = 600000)
    public void alphaMarkingsDoNotChangeDiscoveredNets() throws Exception {
        XLog log = new XesXmlParser().parse(logFile.toFile()).get(0);
        AlphaMinerDiscoverer discoverer = new AlphaMinerDiscoverer(
            new DiscoveryArtifactFactory(new PmnlExporter())
        );
        PipelineRequest.MinerConfig[] variants = {
            TestFixtures.alphaClassic(),
            TestFixtures.alphaVariant("Alpha+", "PLUS"),
            TestFixtures.alphaVariant("Alpha++", "PLUS_PLUS"),
            TestFixtures.alphaVariant("AlphaR", "ROBUST")
        };
        AlphaVersion[] versions = {
            AlphaVersion.CLASSIC, AlphaVersion.PLUS, AlphaVersion.PLUS_PLUS, AlphaVersion.ROBUST
        };
        for (int index = 0; index < variants.length; index++) {
            PipelineRequest.MinerConfig miner = variants[index];
            PipelineRequest request = TestFixtures.buildRequest(
                "alpha_net_" + index, logFile.toString(), TestFixtures.matrixFilter(),
                miner, TestFixtures.defaultMetrics()
            );
            CLIPluginContext oldContext = new CLIPluginContext(new CLIContext(), "alpha-old-" + index);
            Object[] oldResult;
            if (versions[index] == AlphaVersion.ROBUST) {
                oldResult = AlphaMinerPlugin.apply(
                    oldContext, log, new XEventNameClassifier(),
                    new AlphaRobustMinerParameters(AlphaVersion.ROBUST)
                );
            } else {
                oldResult = AlphaMinerPlugin.apply(oldContext, log, new XEventNameClassifier(), versions[index]);
            }
            CLIPluginContext newContext = new CLIPluginContext(new CLIContext(), "alpha-new-" + index);
            DiscoveryArtifact adapted = discoverer.discover(newContext, log, request);
            assertEquals(miner.variant, netStructure((Petrinet) oldResult[0]), netStructure(adapted.getNet()));
            assertTrue(adapted.getNet().getPlaces().containsAll(adapted.getInitialMarking().baseSet()));
            assertTrue(adapted.getNet().getPlaces().containsAll(adapted.getFinalMarking().baseSet()));
        }
    }

    @Test(timeout = 600000)
    public void heuristicsAlternativeEndsAreEvaluatedAsTwoFinalMarkings() throws Exception {
        Path alternatives = TestFixtures.createAlternativeEndsLog(workDir, "alternative-ends.xes");
        PipelineRequest.MinerConfig[] variants = {
            TestFixtures.heuristicsHm(),
            TestFixtures.heuristicsVariant("Flexible Heuristics Miner")
        };
        String[] modes = {"replay-token"};
        for (int index = 0; index < variants.length; index++) {
            for (String mode : modes) {
                String experimentId = "heuristics_alternative_" + index + "_" + mode;
                PipelineRequest request = TestFixtures.buildRequest(
                    experimentId, alternatives.toString(), null, variants[index], TestFixtures.defaultMetrics()
                );
                request.conformance_mode = mode;
                EvaluationResult result = evaluator.evaluate(request);
                assertEvaluationMetrics(result);
                ArtifactBulkResponse bulk = store.readBulk(
                    experimentId, Arrays.asList(result.evaluation_id), true
                );
                ArtifactBulkResponse.ArtifactEntry artifact = bulk.artifacts.get(0);
                assertEquals("both alternative endings must be retained", 2, artifact.final_markings.size());
                assertEquals(Boolean.FALSE, artifact.is_feasible);
                assertTrue(artifact.constraint_violations.contains("MULTIPLE_FINAL_MARKINGS"));
                assertV3Semantics(artifact);
            }
        }
    }

    @Test(timeout = 600000)
    public void allPreprocessingsAreAcceptedAndPersisted() throws Exception {
        List<PipelineRequest.PreprocessingConfig> preprocessings = TestFixtures.allPreprocessings();

        for (PipelineRequest.PreprocessingConfig preprocessing : preprocessings) {
            String experimentId = "real_pre_" + preprocessing.key;
            PipelineRequest request = TestFixtures.buildRequest(
                experimentId,
                logFile.toString(),
                preprocessing,
                TestFixtures.inductiveImf(),
                TestFixtures.defaultMetrics()
            );

            request.conformance_mode = "replay-token";

            EvaluationResult result = evaluator.evaluate(request);
            assertEquals(experimentId, result.experiment_id);
            assertTrue(result.fingerprint.contains(preprocessing.key));
            assertEvaluationMetrics(result);

            ArtifactBulkResponse bulk = store.readBulk(experimentId, Arrays.asList(result.evaluation_id), true);
            assertEquals(1, bulk.artifacts.size());
            assertEquals(preprocessing.key, bulk.artifacts.get(0).pipeline.preprocessing.key);
            assertTrue(bulk.artifacts.get(0).pnml.contains("pnml"));

            for (PromPipelineEvaluator repeated : Arrays.asList(
                new PromPipelineEvaluator(store, workDir), evaluator)) {
                EvaluationResult actual = repeated.evaluate(request);
                assertEquals(preprocessing.key, result.model_semantic_sha256, actual.model_semantic_sha256);
                assertEquals(preprocessing.key, result.metrics, actual.metrics);
                assertEquals(preprocessing.key, result.is_feasible, actual.is_feasible);
                assertEquals(preprocessing.key, result.constraint_violations, actual.constraint_violations);
            }
        }
    }

    private static void assertEvaluationMetrics(EvaluationResult result) {
        if (Boolean.FALSE.equals(result.is_feasible)) {
            assertEquals("skipped_infeasible", result.metrics_status);
            assertTrue(result.metrics.isEmpty());
        } else {
            assertEquals("computed", result.metrics_status);
            TestFixtures.assertMetricsRange(result.metrics, TestFixtures.defaultMetrics());
        }
    }

    @Test(timeout = 600000)
    public void repeatedAndParallelDiscoveriesHaveIdenticalScientificOutcomes() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            int variant = 0;
            for (final PipelineRequest.MinerConfig miner : TestFixtures.activeMinerVariants()) {
                final String prefix = "repro_native_" + variant++;
                PipelineRequest request = TestFixtures.buildRequest(prefix + "_reference", logFile.toString(),
                    TestFixtures.matrixFilter(), miner, TestFixtures.defaultMetrics());
                request.conformance_mode = "replay-token";
                EvaluationResult expected = evaluator.evaluate(request);
                assertEquals("minersweeper-evaluation-v2", expected.evaluation_policy_version);
                assertNotNull(expected.model_semantic_sha256);
                List<Future<EvaluationResult>> repeated = new ArrayList<Future<EvaluationResult>>();
                for (int repetition = 0; repetition < 4; repetition++) {
                    final int index = repetition;
                    repeated.add(pool.submit(new Callable<EvaluationResult>() {
                        @Override public EvaluationResult call() throws Exception {
                            // New evaluator owns fresh log/filter caches and discovery context.
                            PromPipelineEvaluator selected = index == 0
                                ? new PromPipelineEvaluator(store, workDir) : evaluator;
                            PipelineRequest next = TestFixtures.buildRequest(prefix + "_" + index,
                                logFile.toString(), TestFixtures.matrixFilter(), miner, TestFixtures.defaultMetrics());
                            next.conformance_mode = "replay-token";
                            return selected.evaluate(next);
                        }
                    }));
                }
                for (Future<EvaluationResult> future : repeated) {
                    EvaluationResult actual = future.get();
                    assertEquals(miner.variant, expected.model_semantic_sha256, actual.model_semantic_sha256);
                    assertEquals(miner.variant, expected.metrics, actual.metrics);
                    assertEquals(miner.variant, expected.is_feasible, actual.is_feasible);
                    assertEquals(miner.variant, expected.constraint_violations, actual.constraint_violations);
                }
            }
        } finally { pool.shutdownNow(); }
    }

    private static Path resolvePromHome() {
        String env = System.getenv("PROM_HOME");
        if (env != null && !env.trim().isEmpty()) {
            return Paths.get(env.trim()).toAbsolutePath().normalize();
        }
        Path javaServiceDir = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        return javaServiceDir.resolve("..").resolve("..").resolve("tools").resolve("prom-lite-1.4-all-platforms").normalize();
    }

    private static List<String> netStructure(Petrinet net) {
        List<String> structure = new ArrayList<String>();
        for (Place place : net.getPlaces()) {
            List<String> incoming = new ArrayList<String>();
            List<String> outgoing = new ArrayList<String>();
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getInEdges(place)) {
                incoming.add(edge.getSource().getLabel() + edgeWeight(edge));
            }
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getOutEdges(place)) {
                outgoing.add(edge.getTarget().getLabel() + edgeWeight(edge));
            }
            Collections.sort(incoming);
            Collections.sort(outgoing);
            String role = "Start".equals(place.getLabel()) || "End".equals(place.getLabel())
                ? place.getLabel() : "internal";
            structure.add("P:" + role + ":" + incoming + "->" + outgoing);
        }
        for (Transition transition : net.getTransitions()) {
            structure.add("T:" + transition.getLabel() + ":" + transition.isInvisible());
        }
        Collections.sort(structure);
        return structure;
    }

    private static String edgeWeight(PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge) {
        return edge instanceof Arc ? ":" + ((Arc) edge).getWeight() : "";
    }

    private static void assertV3Semantics(ArtifactBulkResponse.ArtifactEntry artifact) throws Exception {
        assertEquals(Integer.valueOf(3), artifact.model_schema_version);
        assertNotNull(artifact.initial_marking);
        assertNotNull(artifact.final_marking);
        assertNotNull(artifact.final_markings);
        assertTrue("at least one real final marking is required", !artifact.final_markings.isEmpty());
        assertMarkingsEqual(artifact.final_marking, artifact.final_markings.get(0));

        Set<String> placeIds = pnmlNodeIds(artifact.pnml, "place");
        assertMarking(artifact.initial_marking, placeIds);
        assertMarking(artifact.final_marking, placeIds);
        for (List<ArtifactBulkResponse.MarkingEntry> marking : artifact.final_markings) {
            assertMarking(marking, placeIds);
        }

        assertNotNull(artifact.transitions);
        Set<String> transitionIds = pnmlNodeIds(artifact.pnml, "transition");
        assertEquals(transitionIds.size(), artifact.transitions.size());
        int actualVisibleCount = 0;
        for (ArtifactBulkResponse.TransitionEntry transition : artifact.transitions) {
            assertTrue("transition ID must exist in PNML", transitionIds.contains(transition.id));
            if (!transition.invisible) {
                actualVisibleCount++;
            }
        }
        assertEquals(Integer.valueOf(actualVisibleCount), artifact.visible_transition_count);
        assertNotNull(artifact.is_feasible);
        assertNotNull(artifact.constraint_violations);
        assertEquals(Boolean.valueOf(artifact.constraint_violations.isEmpty()), artifact.is_feasible);
        assertEquals(Boolean.valueOf(actualVisibleCount == 0),
            Boolean.valueOf(artifact.constraint_violations.contains("NO_VISIBLE_TRANSITIONS")));
        assertEquals(Boolean.valueOf(artifact.final_markings.size() != 1),
            Boolean.valueOf(artifact.constraint_violations.contains("MULTIPLE_FINAL_MARKINGS")));
    }

    private static void assertMarking(
        List<ArtifactBulkResponse.MarkingEntry> marking,
        Set<String> placeIds
    ) {
        assertNotNull(marking);
        for (ArtifactBulkResponse.MarkingEntry entry : marking) {
            assertTrue("marking place ID must exist in PNML", placeIds.contains(entry.place_id));
            assertTrue("marking multiplicity must be positive", entry.tokens > 0);
        }
    }

    private static void assertMarkingsEqual(
        List<ArtifactBulkResponse.MarkingEntry> expected,
        List<ArtifactBulkResponse.MarkingEntry> actual
    ) {
        assertEquals(expected.size(), actual.size());
        for (int index = 0; index < expected.size(); index++) {
            assertEquals(expected.get(index).place_id, actual.get(index).place_id);
            assertEquals(expected.get(index).tokens, actual.get(index).tokens);
        }
    }

    private static Set<String> pnmlNodeIds(String pnml, String nodeName) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        Document document = factory.newDocumentBuilder().parse(
            new ByteArrayInputStream(pnml.getBytes(StandardCharsets.UTF_8))
        );
        NodeList nodes = document.getElementsByTagNameNS("*", nodeName);
        if (nodes.getLength() == 0) {
            nodes = document.getElementsByTagName(nodeName);
        }
        Set<String> ids = new HashSet<String>();
        for (int index = 0; index < nodes.getLength(); index++) {
            Element node = (Element) nodes.item(index);
            if (!node.hasAttribute("idref")) ids.add(node.getAttribute("id"));
        }
        return ids;
    }

    private static Path findLpSolveNativeDir(Path promHome) throws Exception {
        try (java.util.stream.Stream<Path> stream = Files.walk(promHome)) {
            Path lib = stream
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().equals("liblpsolve55.so"))
                .findFirst()
                .orElse(null);
            return lib == null ? null : lib.getParent();
        }
    }
}
