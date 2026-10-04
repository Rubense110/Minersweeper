package com.minersweeper.javaservice.evaluation;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMetricsCalculator;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMode;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.AlphaMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.HeuristicsMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.HybridIlpMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.IlpMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.InductiveMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.SplitMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.fingerprint.FingerprintBuilder;
import com.minersweeper.javaservice.evaluation.io.LogLoader;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import com.minersweeper.javaservice.evaluation.preprocessing.PreprocessingPipeline;
import com.minersweeper.javaservice.evaluation.quality.ModelQualityAnalyzer;
import com.minersweeper.javaservice.evaluation.serialization.PetriNetSemanticsSerializer;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import java.io.InterruptedIOException;
import java.nio.channels.ClosedByInterruptException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CancellationException;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;

public class PromPipelineEvaluator implements PipelineEvaluator {
    private final ArtifactStore artifactStore;
    private final EvaluationAdmission admission = new EvaluationAdmission();
    private final LogLoader logLoader;
    private final Map<String, MinerDiscoverer> minersByKey;
    private final ExperimentExecutionRegistry executionRegistry;
    private final PreprocessingPipeline preprocessingPipeline = new PreprocessingPipeline();

    private final FingerprintBuilder fingerprintBuilder = new FingerprintBuilder();
    private final ConformanceMetricsCalculator conformanceMetricsCalculator = new ConformanceMetricsCalculator();
    private final PetriNetSemanticsSerializer semanticsSerializer = new PetriNetSemanticsSerializer();
    private final ModelQualityAnalyzer qualityAnalyzer = new ModelQualityAnalyzer();

    public PromPipelineEvaluator(ArtifactStore artifactStore, Path logsRoot) {
        this(artifactStore, logsRoot, new ExperimentExecutionRegistry());
    }

    public PromPipelineEvaluator(
        ArtifactStore artifactStore,
        Path logsRoot,
        ExperimentExecutionRegistry executionRegistry
    ) {
        this.artifactStore = artifactStore;
        Path effectiveLogsRoot = logsRoot == null ? Paths.get(".") : logsRoot;
        this.logLoader = new LogLoader(effectiveLogsRoot);
        this.executionRegistry = executionRegistry == null ? new ExperimentExecutionRegistry() : executionRegistry;
        this.minersByKey = createMiners();
    }

    private static ManagedCLIContext createManagedContext(TimingTrace timing) {
        long started = TimingTrace.nowNs();
        ManagedCLIContext context = new ManagedCLIContext();
        timing.markFromStart("context_create_ms", started);
        return context;
    }

    @Override
    public EvaluationResult evaluate(PipelineRequest request) throws Exception {
        TimingTrace timing = TimingTrace.start();
        long evaluationStartNs = TimingTrace.nowNs();
        boolean failed = false;
        String failureType = "";

        String experimentId = TextUtils.safe(request == null ? null : request.experiment_id);
        String requestId = TextUtils.safe(request == null ? null : request.request_id);
        String requestedMetrics = joinMetrics(request);
        String pipelineSummary = summarizePipeline(request);
        ConformanceMode conformanceMode = ConformanceMode.resolve(request.conformance_mode);
        timing.putField("conformance_mode", conformanceMode.key());

        try (ExperimentExecutionRegistry.EvaluationLease ignored = executionRegistry.registerEvaluation(experimentId, requestId);
             EvaluationAdmission.Permit permit = admission.acquire(executionRegistry, experimentId, requestId);
             ManagedCLIContext contexts = createManagedContext(timing)) {
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);
            long logLoadStartNs = TimingTrace.nowNs();
            LogLoader.LogAccess logAccess = logLoader.loadForExperiment(request.experiment_id, request.log_path);
            XLog log = logAccess.log();
            timing.putField("log_cache", logAccess.cacheHit() ? "hit" : "miss");
            timing.markFromStart("log_load_ms", logLoadStartNs);
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);

            PluginContext context = contexts.plugin();
            timing.putField("evaluations_active", Integer.toString(admission.active()));
            timing.putField("evaluations_waiting", Integer.toString(admission.waiting()));
            timing.putField("im_multithreading_effective", Boolean.toString(
                "inductive".equals(request.pipeline.miner.key)
                && Boolean.parseBoolean(System.getenv("PROM_ALLOW_MINER_MULTITHREADING"))
                && com.minersweeper.javaservice.evaluation.utils.ParameterReader.boolParam(
                    request.pipeline.miner.parameters, "use_multithreading", false)));

            long preprocessStartNs = TimingTrace.nowNs();
            PreprocessingPipeline.Access preprocessing = preprocessingPipeline.applyWithCache(context, log, request);
            XLog processedLog = preprocessing.log();
            timing.putField("preprocess_cache", preprocessing.cacheStatus());
            timing.markFromStart("preprocess_ms", preprocessStartNs);
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);

            long discoverStartNs = TimingTrace.nowNs();
            DiscoveryArtifact discovered = discoverModel(context, processedLog, request);
            timing.markFromStart("discover_ms", discoverStartNs);
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);
            int visibleTransitionCount = semanticsSerializer.countVisibleTransitions(discovered.getNet());
            long qualityStartNs = TimingTrace.nowNs();
            ModelQualityAnalyzer.Result quality = qualityAnalyzer.analyze(
                discovered.getNet(), discovered.getInitialMarking(), discovered.getFinalMarkings()
            );
            timing.markFromStart("quality_ms", qualityStartNs);
            List<String> constraintViolations = quality.violations();
            boolean isFeasible = constraintViolations.isEmpty();
            timing.putField("quality_states", Integer.toString(quality.exploredStates));
            timing.putField("quality_feasible", Boolean.toString(isFeasible));
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);

            long metricsStartNs = TimingTrace.nowNs();
            Map<String, Double> canonicalMetrics = isFeasible ? conformanceMetricsCalculator.compute(
                context,
                log,
                discovered.getNet(),
                discovered.getInitialMarking(),
                discovered.getFinalMarkings(),
                request.metrics,
                conformanceMode,
                timing,
                executionRegistry,
                experimentId,
                requestId
            ) : Collections.<String, Double>emptyMap();
            timing.putField("metrics_status", isFeasible ? "computed" : "skipped_infeasible");
            timing.markFromStart("metrics_ms", metricsStartNs);
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);

            Map<String, Double> selectedMetrics = new LinkedHashMap<String, Double>();
            for (String metricName : request.metrics) {
                Double value = canonicalMetrics.get(metricName);
                if (!isFeasible) continue;
                if (value == null) {
                    throw new IllegalArgumentException("unsupported metric: " + metricName);
                }
                selectedMetrics.put(metricName, value);
            }

            long fingerprintStartNs = TimingTrace.nowNs();
            String fingerprint = fingerprintBuilder.buildFingerprint(request);
            timing.markFromStart("fingerprint_ms", fingerprintStartNs);

            long artifactStoreStartNs = TimingTrace.nowNs();
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);
            long pnmlStartNs = TimingTrace.nowNs();
            String pnml = discovered.getPnml();
            PetriNetSemanticsSerializer.SerializedSemantics semantics = semanticsSerializer.serializeAll(
                discovered.getNet(), pnml, discovered.getInitialMarking(), discovered.getFinalMarkings());
            timing.markFromStart("pnml_semantics_ms", pnmlStartNs);
            executionRegistry.throwIfCancellationRequested(experimentId, requestId);
            EvaluationResult result = artifactStore.store(
                request,
                selectedMetrics,
                pnml,
                fingerprint,
                Integer.valueOf(3),
                Integer.valueOf(visibleTransitionCount),
                Boolean.valueOf(isFeasible),
                constraintViolations,
                semantics.initial,
                semantics.finals.get(0),
                semantics.finals,
                semantics.transitions
            );
            timing.markFromStart("store_artifact_ms", artifactStoreStartNs);
            result.metrics_status = isFeasible ? "computed" : "skipped_infeasible";
            result.evaluation_policy_version = "minersweeper-evaluation-v2";
            result.model_semantic_sha256 = quality.modelSemanticHash;
            result.discovery_metadata = discovered.getDiscoveryMetadata();
            result.evaluation_environment = com.minersweeper.javaservice.evaluation.reproducibility.EvaluationEnvironment.current();
            return result;
        } catch (Exception error) {
            Exception effectiveError = normalizeCancellationFailure(experimentId, requestId, error);
            failed = true;
            failureType = effectiveError.getClass().getSimpleName();
            throw effectiveError;
        } finally {
            long totalMs = TimingTrace.elapsedMs(evaluationStartNs);
            timing.logSummary(
                totalMs,
                failed,
                failureType,
                experimentId,
                pipelineSummary,
                requestedMetrics
            );
        }
    }

    @Override
    public void cancelExperiment(String experimentId) {
        executionRegistry.requestCancel(experimentId);
    }

    @Override
    public void cancelEvaluation(String experimentId, String requestId) {
        executionRegistry.requestCancelEvaluation(experimentId, requestId);
    }

    @Override
    public Boolean terminationConfirmed(String experimentId, String requestId) {
        return executionRegistry.terminationConfirmed(experimentId, requestId);
    }

    @Override
    public void cleanupExperiment(String experimentId) throws Exception {
        executionRegistry.cleanupExperiment(experimentId);
        preprocessingPipeline.evictExperiment(experimentId);
        logLoader.evictExperiment(experimentId);
    }

    private Exception normalizeCancellationFailure(String experimentId, String requestId, Exception error) {
        if (error instanceof ExperimentCancelledException) {
            clearInterruptedStatus();
            return error;
        }
        if (!executionRegistry.isCancellationRequested(experimentId, requestId)) {
            return error;
        }
        if (!Thread.currentThread().isInterrupted() && !isInterruptedFailure(error)) {
            return error;
        }
        clearInterruptedStatus();
        return new ExperimentCancelledException("experiment '" + experimentId + "' cancelled");
    }

    private static boolean isInterruptedFailure(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (
                current instanceof InterruptedException
                || current instanceof InterruptedIOException
                || current instanceof ClosedByInterruptException
                || current instanceof CancellationException
            ) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static void clearInterruptedStatus() {
        Thread.interrupted();
    }

    private DiscoveryArtifact discoverModel(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        String minerKey = TextUtils.safe(request.pipeline.miner.key).toLowerCase();
        if (isExcludedByRequest(request, minerKey)) {
            throw new IllegalArgumentException("miner excluded by request: " + minerKey);
        }
        MinerDiscoverer discoverer = minersByKey.get(minerKey);
        if (discoverer == null) {
            throw new IllegalArgumentException("unsupported miner for real evaluator: " + minerKey);
        }
        return discoverer.discover(context, log, request);
    }

    private Map<String, MinerDiscoverer> createMiners() {
        DiscoveryArtifactFactory artifactFactory = new DiscoveryArtifactFactory(new PmnlExporter());
        Map<String, MinerDiscoverer> discoverers = new LinkedHashMap<String, MinerDiscoverer>();
        register(discoverers, new AlphaMinerDiscoverer(artifactFactory));
        register(discoverers, new InductiveMinerDiscoverer(artifactFactory, executionRegistry));
        register(discoverers, new HeuristicsMinerDiscoverer(artifactFactory));
        register(discoverers, new SplitMinerDiscoverer(artifactFactory));
        register(discoverers, new IlpMinerDiscoverer(artifactFactory));
        register(discoverers, new HybridIlpMinerDiscoverer(artifactFactory));
        return Collections.unmodifiableMap(discoverers);
    }

    private void register(Map<String, MinerDiscoverer> discoverers, MinerDiscoverer discoverer) {
        discoverers.put(discoverer.key(), discoverer);
    }

    private boolean isExcludedByRequest(PipelineRequest request, String minerKey) {
        if (request == null || request.excluded_miners == null || request.excluded_miners.isEmpty()) {
            return false;
        }
        for (String excluded : request.excluded_miners) {
            if (minerKey.equals(TextUtils.safe(excluded).toLowerCase())) {
                return true;
            }
        }
        return false;
    }

    private static String joinMetrics(PipelineRequest request) {
        if (request == null || request.metrics == null || request.metrics.isEmpty()) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (String metric : request.metrics) {
            if (out.length() > 0) {
                out.append(',');
            }
            out.append(TextUtils.safe(metric));
        }
        return out.toString();
    }

    private static String summarizePipeline(PipelineRequest request) {
        if (request == null || request.pipeline == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(192);
        appendPreprocessingSummaries(out, request.pipeline);
        appendMinerSummary(out, request.pipeline.miner);
        return out.toString();
    }

    private static void appendPreprocessingSummaries(StringBuilder out, PipelineRequest.PipelineConfig pipeline) {
        if (pipeline == null) {
            return;
        }
        List<PipelineRequest.PreprocessingConfig> preprocessings = pipeline.preprocessings;
        if (preprocessings == null || preprocessings.isEmpty()) {
            appendPreprocessingSummary(out, pipeline.preprocessing, 0);
            return;
        }
        for (int i = 0; i < preprocessings.size(); i++) {
            appendPreprocessingSummary(out, preprocessings.get(i), i);
        }
    }

    private static void appendPreprocessingSummary(
        StringBuilder out,
        PipelineRequest.PreprocessingConfig preprocessing,
        int index
    ) {
        if (preprocessing == null) {
            return;
        }
        appendSectionStart(out, "pre" + index);
        appendNamedValue(out, "key", preprocessing.key);
        appendNamedValue(out, "method", preprocessing.method);
        appendNamedValue(out, "variant", preprocessing.variant);
        appendParameters(out, preprocessing.parameters);
        out.append('}');
    }

    private static void appendMinerSummary(StringBuilder out, PipelineRequest.MinerConfig miner) {
        if (miner == null) {
            return;
        }
        appendSectionStart(out, "miner");
        appendNamedValue(out, "key", miner.key);
        appendNamedValue(out, "family", miner.family);
        appendNamedValue(out, "variant", miner.variant);
        appendParameters(out, miner.parameters);
        out.append('}');
    }

    private static void appendSectionStart(StringBuilder out, String section) {
        if (out.length() > 0) {
            out.append('|');
        }
        out.append(section).append('{');
    }

    private static void appendNamedValue(StringBuilder out, String key, String value) {
        String safeValue = TextUtils.safe(value);
        if (safeValue.isEmpty()) {
            return;
        }
        if (out.charAt(out.length() - 1) != '{') {
            out.append(',');
        }
        out.append(key).append('=').append(safeValue);
    }

    private static void appendParameters(StringBuilder out, Map<String, Object> parameters) {
        if (parameters == null || parameters.isEmpty()) {
            return;
        }
        List<String> names = new ArrayList<String>(parameters.keySet());
        Collections.sort(names);

        if (out.charAt(out.length() - 1) != '{') {
            out.append(',');
        }
        out.append("params=");
        for (int i = 0; i < names.size(); i++) {
            if (i > 0) {
                out.append(';');
            }
            String name = names.get(i);
            out.append(TextUtils.safe(name));
            out.append(':');
            out.append(TextUtils.safeObj(parameters.get(name)));
        }
    }
}
