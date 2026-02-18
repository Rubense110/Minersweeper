package com.minersweeper.javaservice.evaluation;

import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.fingerprint.FingerprintBuilder;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import com.minersweeper.javaservice.evaluation.io.LogLoader;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfo;
import org.deckfour.xes.info.XLogInfoFactory;
import org.deckfour.xes.model.XLog;
import org.processmining.acceptingpetrinet.models.AcceptingPetriNet;
import org.processmining.alphaminer.parameters.AlphaRobustMinerParameters;
import org.processmining.alphaminer.parameters.AlphaVersion;
import org.processmining.alphaminer.plugins.AlphaMinerPlugin;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.framework.packages.PackageManager.Canceller;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.hybridilpminer.parameters.DiscoveryStrategy;
import org.processmining.hybridilpminer.parameters.DiscoveryStrategyType;
import org.processmining.hybridilpminer.parameters.LPFilter;
import org.processmining.hybridilpminer.parameters.LPFilterType;
import org.processmining.hybridilpminer.parameters.LPObjectiveType;
import org.processmining.hybridilpminer.parameters.LPVariableType;
import org.processmining.hybridilpminer.parameters.XLogHybridILPMinerParametersImpl;
import org.processmining.hybridilpminer.plugins.HybridILPMinerPlugin;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.heuristics.HeuristicsNet;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.InductiveMiner.mining.logs.LifeCycleClassifier;
import org.processmining.plugins.InductiveMiner.mining.logs.XLifeCycleClassifier;
import org.processmining.plugins.astar.petrinet.PetrinetReplayerWithILP;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;
import org.processmining.plugins.heuristicsnet.miner.heuristics.converter.HeuristicsNetToPetriNetConverter;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.FlexibleHeuristicsMinerPlugin;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.HeuristicsMiner;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.settings.HeuristicsMinerSettings;
import org.processmining.plugins.ilpminer.ILPMiner;
import org.processmining.plugins.ilpminer.ILPMinerSettings;
import org.processmining.plugins.ilpminer.ILPMinerSettings.SolverSetting;
import org.processmining.plugins.ilpminer.ILPMinerSettings.SolverType;
import org.processmining.plugins.ilpminer.templates.PetriNetILPModelSettings;
import org.processmining.plugins.ilpminer.templates.PetriNetILPModelSettings.SearchType;
import org.processmining.plugins.ilpminer.templates.PetriNetVariableFitnessILPModelSettings;
import org.processmining.plugins.ilpminer.templates.javailp.PetriNetILPModel;
import org.processmining.plugins.ilpminer.templates.javailp.PetriNetVariableFitnessILPModel;
import org.processmining.plugins.inductiveminer2.logs.IMLog;
import org.processmining.plugins.inductiveminer2.logs.IMLogImpl;
import org.processmining.plugins.inductiveminer2.logs.IMLogImplPartialTraces;
import org.processmining.plugins.inductiveminer2.mining.MiningParameters;
import org.processmining.plugins.inductiveminer2.mining.MiningParametersAbstract;
import org.processmining.plugins.inductiveminer2.plugins.InductiveMinerPlugin;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIM;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMInfrequent;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMInfrequentLifeCycle;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMInfrequentPartialTraces;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMInfrequentPartialTracesAli;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMLifeCycle;
import org.processmining.plugins.inductiveminer2.variants.MiningParametersIMPartialTraces;
import org.processmining.plugins.petrinet.replayer.PNLogReplayer;
import org.processmining.plugins.petrinet.replayer.algorithms.costbasedcomplete.CostBasedCompleteParam;
import org.processmining.plugins.petrinet.replayresult.PNRepResult;
import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGen;
import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGenRes;

public class PromPipelineEvaluator implements PipelineEvaluator {
    private static final String METRIC_GENERALISATION = "generalisation";
    private static final String METRIC_GENERALIZATION = "generalization";

    private final ArtifactStore artifactStore;
    private final Path logsRoot;
    private final LogLoader logLoader;

    private final FingerprintBuilder fingerprintBuilder = new FingerprintBuilder();
    private final PmnlExporter pmnlExporter = new PmnlExporter();

    public PromPipelineEvaluator(ArtifactStore artifactStore, Path logsRoot) {
        this.artifactStore = artifactStore;
        this.logsRoot = logsRoot == null ? Paths.get(".") : logsRoot;
        this.logLoader = new LogLoader(this.logsRoot);
    }

    @Override
    public EvaluationResult evaluate(PipelineRequest request) throws Exception {
        Path logFile = logLoader.resolveLogPath(request.log_path);
        XLog log = logLoader.loadLog(logFile.toFile());
        PluginContext context = createContext();

        DiscoveryArtifact discovered = discoverModel(context, log, request);
        Map<String, Double> canonicalMetrics = evaluateMetrics(context, log, discovered);

        Map<String, Double> selectedMetrics = new LinkedHashMap<String, Double>();
        for (String metricName : request.metrics) {
            String key = normalizeMetricName(metricName);
            Double value = canonicalMetrics.get(key);
            if (value == null) {
                throw new IllegalArgumentException("unsupported metric: " + metricName);
            }
            selectedMetrics.put(metricName, value);
        }

        String fingerprint = fingerprintBuilder.buildFingerprint(request);
        return artifactStore.store(request, selectedMetrics, discovered.pnml, fingerprint);
    }

    private DiscoveryArtifact discoverModel(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        String minerKey = TextUtils.safe(request.pipeline.miner.key).toLowerCase();

        if ("alpha".equals(minerKey)) {
            return discoverAlpha(context, log, request);
        }
        if ("inductive".equals(minerKey)) {
            return discoverInductive(log, request);
        }
        if ("heuristics".equals(minerKey)) {
            return discoverHeuristics(context, log, request);
        }
        if ("ilp".equals(minerKey)) {
            return discoverIlp(context, log, request);
        }
        if ("hybrid_ilp".equals(minerKey)) {
            return discoverHybridIlp(context, log, request);
        }
        throw new IllegalArgumentException("unsupported miner for real evaluator: " + minerKey);
    }

    private DiscoveryArtifact discoverAlpha(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        AlphaVersion version = mapAlphaVersion(request.pipeline.miner.variant);
        Object[] result;
        if (AlphaVersion.ROBUST.equals(version)) {
            // Do not call applyAlphaRobust/apply(..., AlphaVersion.ROBUST): those paths create
            // AlphaMinerParameters instead of AlphaRobustMinerParameters in this ProM version.
            // That ends in ClassCastException inside AlphaMinerFactory.
            AlphaRobustMinerParameters robustParams = new AlphaRobustMinerParameters(AlphaVersion.ROBUST);
            robustParams.setCausalThreshold(
                ParameterReader.doubleParam(
                    request.pipeline.miner.parameters,
                    "causal_threshold",
                    robustParams.getCausalThreshold()
                )
            );
            robustParams.setNoiseThresholdLeastFreq(
                ParameterReader.doubleParam(
                    request.pipeline.miner.parameters,
                    "noise_threshold_least_freq",
                    robustParams.getNoiseThresholdLeastFreq()
                )
            );
            robustParams.setNoiseThresholdMostFreq(
                ParameterReader.doubleParam(
                    request.pipeline.miner.parameters,
                    "noise_threshold_most_freq",
                    robustParams.getNoiseThresholdMostFreq()
                )
            );
            result = AlphaMinerPlugin.apply(context, log, new XEventNameClassifier(), robustParams);
        } else {
            result = AlphaMinerPlugin.apply(context, log, new XEventNameClassifier(), version);
        }
        return toDiscoveryArtifact(context, result);
    }

    private DiscoveryArtifact discoverInductive(XLog log, PipelineRequest request) throws Exception {
        MiningParameters params = createInductiveParams(request.pipeline.miner.variant);
        if (params instanceof MiningParametersAbstract) {
            MiningParametersAbstract abstractParams = (MiningParametersAbstract) params;
            abstractParams.setClassifier(new XEventNameClassifier());
            abstractParams.setNoiseThreshold(ParameterReader.floatParam(request.pipeline.miner.parameters, "noise_threshold", 0.2f));
            abstractParams.setDebug(ParameterReader.boolParam(request.pipeline.miner.parameters, "is_debug", false));
            abstractParams.setUseMultithreading(ParameterReader.boolParam(request.pipeline.miner.parameters, "use_multithreading", true));
        }

        XEventClassifier classifier = new XEventNameClassifier();
        XLifeCycleClassifier lifeCycleClassifier = new LifeCycleClassifier();
        boolean usePartialTraces = TextUtils.safe(request.pipeline.miner.variant).toLowerCase().contains("partial traces");
        IMLog imLog = usePartialTraces
            ? new IMLogImplPartialTraces(log, classifier, lifeCycleClassifier)
            : new IMLogImpl(log, classifier, lifeCycleClassifier);

        Canceller canceller = new Canceller() {
            @Override
            public boolean isCancelled() {
                return false;
            }
        };

        AcceptingPetriNet apn = InductiveMinerPlugin.minePetriNet(imLog, params, canceller);
        return toDiscoveryArtifact(createContext(), new Object[] { apn });
    }

    private DiscoveryArtifact discoverHeuristics(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        HeuristicsMinerSettings settings = new HeuristicsMinerSettings();
        settings.setClassifier(new XEventNameClassifier());
        settings.setRelativeToBestThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "relative_to_best_threshold", 0.05));
        settings.setPositiveObservationThreshold(ParameterReader.intParam(request.pipeline.miner.parameters, "positive_observation_threshold", 1));
        settings.setDependencyThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "dependency_threshold", 0.90));
        settings.setL1lThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "l1l_threshold", 0.90));
        settings.setL2lThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "l2l_threshold", 0.90));
        settings.setLongDistanceThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "long_distance_threshold", 0.90));
        settings.setDependencyDivisor(ParameterReader.intParam(request.pipeline.miner.parameters, "dependency_divisor", 1));
        settings.setAndThreshold(ParameterReader.doubleParam(request.pipeline.miner.parameters, "and_threshold", 0.10));
        settings.setExtraInfo(ParameterReader.boolParam(request.pipeline.miner.parameters, "extra_info", false));
        settings.setUseAllConnectedHeuristics(ParameterReader.boolParam(request.pipeline.miner.parameters, "use_all_connected_heuristics", true));
        settings.setUseLongDistanceDependency(ParameterReader.boolParam(request.pipeline.miner.parameters, "use_long_distance_dependency", false));
        settings.setCheckBestAgainstL2L(ParameterReader.boolParam(request.pipeline.miner.parameters, "check_best_against_l2l", true));

        HeuristicsNet heuristicsNet;
        boolean flexible = TextUtils.safe(request.pipeline.miner.variant).toLowerCase().contains("flexible");
        if (flexible) {
            heuristicsNet = FlexibleHeuristicsMinerPlugin.run(context, log, settings);
        } else {
            HeuristicsMiner miner = new HeuristicsMiner(context, log, settings);
            heuristicsNet = miner.mine();
        }

        Object[] result = HeuristicsNetToPetriNetConverter.converter(context, heuristicsNet);
        return toDiscoveryArtifact(context, result);
    }

    private DiscoveryArtifact discoverIlp(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        ILPMiner ilpMiner = new ILPMiner();
        ILPMinerSettings settings = new ILPMinerSettings();

        SolverType solverType = solverTypeByName(TextUtils.safeObj(request.pipeline.miner.parameters.get("solver_type")), SolverType.JAVAILP_LPSOLVE);
        settings.setSolverSetting(SolverSetting.TYPE, solverType);
        settings.setSolverSetting(
            SolverSetting.LICENSE_DIR,
            TextUtils.safeOrDefault(request.pipeline.miner.parameters.get("license_dir"), "c:\\\\ILOG\\\\ILM")
        );

        String variant = TextUtils.safe(request.pipeline.miner.variant).toLowerCase();
        boolean variableFitness = variant.contains("variable fitness");

        PetriNetILPModelSettings modelSettings;
        if (variableFitness) {
            PetriNetVariableFitnessILPModelSettings variableSettings = new PetriNetVariableFitnessILPModelSettings();
            variableSettings.setFitness(ParameterReader.doubleParam(request.pipeline.miner.parameters, "fitness", 0.0));
            modelSettings = variableSettings;
            settings.setVariant(PetriNetVariableFitnessILPModel.class);
        } else {
            modelSettings = new PetriNetILPModelSettings();
            settings.setVariant(PetriNetILPModel.class);
        }

        SearchType searchType = searchTypeByName(TextUtils.safeObj(request.pipeline.miner.parameters.get("search_type")), SearchType.PER_CD);
        modelSettings.setSearchType(searchType);
        modelSettings.setSeparateInitialPlaces(ParameterReader.boolParam(request.pipeline.miner.parameters, "separate_initial_places", true));
        settings.setModelSettings(modelSettings);

        XLogInfo logInfo = XLogInfoFactory.createLogInfo(log, new XEventNameClassifier());
        Object[] result;
        try {
            result = ilpMiner.doILPMiningWithSettings(context, log, logInfo, settings);
        } catch (NullPointerException npe) {
            throw new IllegalArgumentException(
                "ILP miner failed in the current ProM headless context (log-relations plugin returned null). " +
                "Use hybrid_ilp or disable ilp for this run.",
                npe
            );
        }
        if (result == null) {
            throw new IllegalArgumentException(
                "ILP miner returned no result in the current ProM headless context. Use hybrid_ilp or disable ilp."
            );
        }
        return toDiscoveryArtifact(context, result);
    }

    private DiscoveryArtifact discoverHybridIlp(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        XLogHybridILPMinerParametersImpl params = new XLogHybridILPMinerParametersImpl(context, log, new XEventNameClassifier());

        params.setObjectiveType(lpObjectiveByName(mapHybridObjective(TextUtils.safeObj(request.pipeline.miner.parameters.get("lp_objective"))), LPObjectiveType.MINIMIZE_ARCS));
        params.setVariableType(lpVariableByName(mapHybridVariable(TextUtils.safeObj(request.pipeline.miner.parameters.get("lp_variable_type"))), LPVariableType.DUAL));

        LPFilterType filterType = lpFilterTypeByName(mapHybridFilterType(TextUtils.safeObj(request.pipeline.miner.parameters.get("lp_filter"))), LPFilterType.NONE);
        LPFilter filter = new LPFilter(filterType, hybridFilterThreshold(request.pipeline.miner.parameters));
        params.setFilter(filter);

        DiscoveryStrategyType discoveryType = discoveryStrategyByName(
            mapHybridDiscoveryStrategy(TextUtils.safeObj(request.pipeline.miner.parameters.get("discovery_strategy"))),
            DiscoveryStrategyType.CAUSAL
        );
        params.setDiscoveryStrategy(new DiscoveryStrategy(discoveryType));

        Object[] result = HybridILPMinerPlugin.applyParams(context, log, params);
        return toDiscoveryArtifact(context, result);
    }

    private Map<String, Double> evaluateMetrics(PluginContext context, XLog log, DiscoveryArtifact artifact) throws Exception {
        Marking initial = artifact.initialMarking != null ? artifact.initialMarking : deriveInitialMarking(artifact.net);
        Marking fin = artifact.finalMarking != null ? artifact.finalMarking : deriveFinalMarking(artifact.net);

        ConformanceResult conformance = computeConformance(context, log, artifact.net, initial, fin);

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", MetricUtils.clamp01(conformance.fitness));
        metrics.put("precision", MetricUtils.clamp01(conformance.precision));
        metrics.put(METRIC_GENERALISATION, MetricUtils.clamp01(conformance.generalisation));
        metrics.put("simplicity", MetricUtils.clamp01(computeStructuralSimplicity(artifact.net)));
        return metrics;
    }

    private ConformanceResult computeConformance(PluginContext context, XLog log, Petrinet net, Marking initial, Marking fin) throws Exception {
        XEventClassifier classifier = new XEventNameClassifier();
        XLogInfo logInfo = XLogInfoFactory.createLogInfo(log, classifier);
        XEventClasses eventClasses = logInfo.getEventClasses();
        XEventClass dummy = new XEventClass("DUMMY", eventClasses.size() + 1);

        TransEvClassMapping mapping = new TransEvClassMapping(classifier, dummy);
        for (Transition transition : net.getTransitions()) {
            XEventClass targetClass = null;
            if (!transition.isInvisible()) {
                targetClass = eventClasses.getByIdentity(transition.getLabel());
                if (targetClass == null) {
                    targetClass = eventClasses.getByIdentity(transition.getLabel() + "+complete");
                }
            }
            mapping.put(transition, targetClass != null ? targetClass : dummy);
        }

        CostBasedCompleteParam replayParam = new CostBasedCompleteParam(
            eventClasses.getClasses(),
            dummy,
            net.getTransitions(),
            1,
            1
        );
        replayParam.setInitialMarking(initial);
        replayParam.setFinalMarkings(fin);
        replayParam.setCreateConn(false);
        replayParam.setGUIMode(false);
        replayParam.setNumThreads(1);

        PNLogReplayer replayer = new PNLogReplayer();
        PetrinetReplayerWithILP replayAlgorithm = new PetrinetReplayerWithILP();
        PNRepResult replayResult = replayer.replayLog(context, net, log, mapping, replayAlgorithm, replayParam);

        Map<String, Object> info = replayResult.getInfo();
        double fitness = MetricUtils.toDouble(info.get(PNRepResult.TRACEFITNESS), 0.0);

        AlignmentPrecGen alignmentPrecGen = new AlignmentPrecGen();
        AlignmentPrecGenRes precisionGeneralization = alignmentPrecGen.measureConformanceAssumingCorrectAlignment(
            context,
            mapping,
            replayResult,
            net,
            initial,
            false
        );

        ConformanceResult result = new ConformanceResult();
        result.fitness = fitness;
        result.precision = precisionGeneralization.getPrecision();
        result.generalisation = precisionGeneralization.getGeneralization();
        return result;
    }

    private DiscoveryArtifact toDiscoveryArtifact(PluginContext context, Object[] resultArray) throws Exception {
        Petrinet net = null;
        Marking initial = null;
        Marking fin = null;

        if (resultArray == null) {
            throw new IllegalStateException("Miner returned null result");
        }

        for (Object item : resultArray) {
            if (item == null) {
                continue;
            }
            if (item instanceof Petrinet) {
                net = (Petrinet) item;
                continue;
            }
            if (item instanceof Marking) {
                if (initial == null) {
                    initial = (Marking) item;
                } else if (fin == null) {
                    fin = (Marking) item;
                }
                continue;
            }
            if (item instanceof AcceptingPetriNet) {
                AcceptingPetriNet apn = (AcceptingPetriNet) item;
                net = apn.getNet();
                initial = apn.getInitialMarking();
                Set<Marking> finals = apn.getFinalMarkings();
                if (finals != null && !finals.isEmpty()) {
                    fin = finals.iterator().next();
                }
            }
        }

        if (net == null) {
            throw new IllegalStateException("Unable to extract Petri net from miner result");
        }

        DiscoveryArtifact artifact = new DiscoveryArtifact();
        artifact.net = net;
        artifact.initialMarking = initial != null ? initial : deriveInitialMarking(net);
        artifact.finalMarking = fin != null ? fin : deriveFinalMarking(net);
        artifact.pnml = pmnlExporter.exportPnml(context, net);
        return artifact;
    }

    private PluginContext createContext() {
        CLIContext global = new CLIContext();
        return new CLIPluginContext(global, "minersweeper");
    }

    private Marking deriveInitialMarking(Petrinet net) {
        Marking marking = new Marking();
        for (Place place : net.getPlaces()) {
            if (net.getInEdges(place).isEmpty()) {
                marking.add(place);
            }
        }
        if (marking.isEmpty() && !net.getPlaces().isEmpty()) {
            marking.add(net.getPlaces().iterator().next());
        }
        return marking;
    }

    private Marking deriveFinalMarking(Petrinet net) {
        Marking marking = new Marking();
        for (Place place : net.getPlaces()) {
            if (net.getOutEdges(place).isEmpty()) {
                marking.add(place);
            }
        }
        if (marking.isEmpty() && !net.getPlaces().isEmpty()) {
            marking.add(net.getPlaces().iterator().next());
        }
        return marking;
    }

    private double computeStructuralSimplicity(Petrinet net) {
        double places = net.getPlaces().size();
        double transitions = net.getTransitions().size();
        double arcs = net.getEdges().size();

        double branchingPenalty = 0.0;
        for (Transition transition : net.getTransitions()) {
            int in = net.getInEdges(transition).size();
            int out = net.getOutEdges(transition).size();
            if (in > 1) {
                branchingPenalty += (in - 1);
            }
            if (out > 1) {
                branchingPenalty += (out - 1);
            }
        }

        double complexity = places + transitions + arcs + branchingPenalty;
        return 1.0 / (1.0 + (complexity / 50.0));
    }

    private MiningParameters createInductiveParams(String variantLabel) {
        String variant = TextUtils.safe(variantLabel).toLowerCase();
        if (variant.contains("imfpta")) {
            return new MiningParametersIMInfrequentPartialTracesAli();
        }
        if (variant.contains("imfpt")) {
            return new MiningParametersIMInfrequentPartialTraces();
        }
        if (variant.contains("imflc")) {
            return new MiningParametersIMInfrequentLifeCycle();
        }
        if (variant.contains("impt")) {
            return new MiningParametersIMPartialTraces();
        }
        if (variant.contains("imlc")) {
            return new MiningParametersIMLifeCycle();
        }
        if (variant.contains("imf")) {
            return new MiningParametersIMInfrequent();
        }
        return new MiningParametersIM();
    }

    private AlphaVersion mapAlphaVersion(String variantLabel) {
        String variant = TextUtils.safe(variantLabel).toLowerCase();
        if (variant.contains("alpha+")) {
            if (variant.contains("++")) {
                return AlphaVersion.PLUS_PLUS;
            }
            return AlphaVersion.PLUS;
        }
        if (variant.contains("alpha#")) {
            return AlphaVersion.SHARP;
        }
        if (variant.contains("alphar")) {
            return AlphaVersion.ROBUST;
        }
        if (variant.contains("robust")) {
            return AlphaVersion.ROBUST;
        }
        if (variant.contains("alpha$")) {
            return AlphaVersion.DOLLAR;
        }
        return AlphaVersion.CLASSIC;
    }

    private SolverType solverTypeByName(String value, SolverType fallback) {
        try {
            return SolverType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private SearchType searchTypeByName(String value, SearchType fallback) {
        try {
            return SearchType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private LPObjectiveType lpObjectiveByName(String value, LPObjectiveType fallback) {
        try {
            return LPObjectiveType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private LPVariableType lpVariableByName(String value, LPVariableType fallback) {
        try {
            return LPVariableType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private LPFilterType lpFilterTypeByName(String value, LPFilterType fallback) {
        try {
            return LPFilterType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private DiscoveryStrategyType discoveryStrategyByName(String value, DiscoveryStrategyType fallback) {
        try {
            return DiscoveryStrategyType.valueOf(value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private String normalizeMetricName(String metric) {
        String normalized = TextUtils.safe(metric).toLowerCase();
        if (METRIC_GENERALIZATION.equals(normalized)) {
            return METRIC_GENERALISATION;
        }
        return normalized;
    }

    private static String mapHybridObjective(String value) {
        String text = TextUtils.safe(value);
        if (text.equalsIgnoreCase("Unweighted Parikh values")) {
            return "UNWEIGHTED_PARIKH";
        }
        if (text.equalsIgnoreCase("Weighted Parikh values, using absolute frequencies")) {
            return "WEIGHTED_ABSOLUTE_PARIKH";
        }
        if (text.equalsIgnoreCase("Weighted Parikh values, using relative frequencies")) {
            return "WEIGHTED_RELATIVE_PARIKH";
        }
        return "MINIMIZE_ARCS";
    }

    private static String mapHybridVariable(String value) {
        String text = TextUtils.safe(value);
        if (text.equalsIgnoreCase("One variable per event")) {
            return "SINGLE";
        }
        if (text.equalsIgnoreCase("One variable per event, two for an event which is potentially in a self loop")) {
            return "HYBRID";
        }
        return "DUAL";
    }

    private static String mapHybridFilterType(String value) {
        String text = TextUtils.safe(value);
        if (text.equalsIgnoreCase("Sequence Encoding Filter")) {
            return "SEQUENCE_ENCODING";
        }
        if (text.equalsIgnoreCase("Slack Variable Filter")) {
            return "SLACK_VAR";
        }
        return "NONE";
    }

    private static String mapHybridDiscoveryStrategy(String value) {
        String text = TextUtils.safe(value);
        if (text.equalsIgnoreCase("Alpha")) {
            return "CAUSAL_E_VERBEEK";
        }
        if (text.equalsIgnoreCase("Heuristics") || text.equalsIgnoreCase("Fuzzy")) {
            return "CAUSAL_FLEX_HEUR";
        }
        if (text.equalsIgnoreCase("Directly Follows")) {
            return "TRANSITION_PAIR";
        }
        return "CAUSAL";
    }

    private static double hybridFilterThreshold(Map<String, Object> parameters) {
        String filterName = TextUtils.safe(parameters.get("lp_filter") != null ? String.valueOf(parameters.get("lp_filter")) : null);
        if (filterName.equalsIgnoreCase("Sequence Encoding Filter")) {
            return ParameterReader.doubleParam(parameters, "sequence_encoding_cutoff_level", 0.0);
        }
        if (filterName.equalsIgnoreCase("Slack Variable Filter")) {
            return ParameterReader.doubleParam(parameters, "slack_variable_filter_threshold", 0.0);
        }
        return 0.0;
    }

    private static class DiscoveryArtifact {
        Petrinet net;
        Marking initialMarking;
        Marking finalMarking;
        String pnml;
    }

    private static class ConformanceResult {
        double fitness;
        double precision;
        double generalisation;
    }
}
