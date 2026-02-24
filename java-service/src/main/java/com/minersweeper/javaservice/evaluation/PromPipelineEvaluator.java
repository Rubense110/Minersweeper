package com.minersweeper.javaservice.evaluation;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.conformance.ConformanceMetricsCalculator;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.AlphaMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.HeuristicsMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.HybridIlpMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.IlpMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.discovery.miners.InductiveMinerDiscoverer;
import com.minersweeper.javaservice.evaluation.fingerprint.FingerprintBuilder;
import com.minersweeper.javaservice.evaluation.io.LogLoader;
import com.minersweeper.javaservice.evaluation.io.PmnlExporter;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.deckfour.xes.model.XLog;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.framework.plugin.PluginContext;

public class PromPipelineEvaluator implements PipelineEvaluator {
    private final ArtifactStore artifactStore;
    private final LogLoader logLoader;
    private final Map<String, MinerDiscoverer> minersByKey;

    private final FingerprintBuilder fingerprintBuilder = new FingerprintBuilder();
    private final ConformanceMetricsCalculator conformanceMetricsCalculator = new ConformanceMetricsCalculator();

    public PromPipelineEvaluator(ArtifactStore artifactStore, Path logsRoot) {
        this.artifactStore = artifactStore;
        Path effectiveLogsRoot = logsRoot == null ? Paths.get(".") : logsRoot;
        this.logLoader = new LogLoader(effectiveLogsRoot);
        this.minersByKey = createMiners();
    }

    @Override
    public EvaluationResult evaluate(PipelineRequest request) throws Exception {
        TimingTrace timing = TimingTrace.start();
        long evaluationStartNs = TimingTrace.nowNs();
        boolean failed = false;
        String failureType = "";

        String experimentId = TextUtils.safe(request == null ? null : request.experiment_id);
        String requestedMetrics = joinMetrics(request);
        String minerKey = "";
        String minerVariant = "";
        String preprocessingKey = "";
        if (request != null && request.pipeline != null) {
            if (request.pipeline.miner != null) {
                minerKey = TextUtils.safe(request.pipeline.miner.key);
                minerVariant = TextUtils.safe(request.pipeline.miner.variant);
            }
            if (request.pipeline.preprocessing != null) {
                preprocessingKey = TextUtils.safe(request.pipeline.preprocessing.key);
            }
        }

        try {
            long logLoadStartNs = TimingTrace.nowNs();
            Path logFile = logLoader.resolveLogPath(request.log_path);
            XLog log = logLoader.loadLog(logFile.toFile());
            timing.markFromStart("log_load_ms", logLoadStartNs);

            long contextStartNs = TimingTrace.nowNs();
            PluginContext context = createContext();
            timing.markFromStart("context_create_ms", contextStartNs);

            long discoverStartNs = TimingTrace.nowNs();
            DiscoveryArtifact discovered = discoverModel(context, log, request);
            timing.markFromStart("discover_ms", discoverStartNs);

            long metricsStartNs = TimingTrace.nowNs();
            Map<String, Double> canonicalMetrics = conformanceMetricsCalculator.compute(
                context,
                log,
                discovered.getNet(),
                discovered.getInitialMarking(),
                discovered.getFinalMarking(),
                request.metrics,
                timing
            );
            timing.markFromStart("metrics_ms", metricsStartNs);

            Map<String, Double> selectedMetrics = new LinkedHashMap<String, Double>();
            for (String metricName : request.metrics) {
                Double value = canonicalMetrics.get(metricName);
                if (value == null) {
                    throw new IllegalArgumentException("unsupported metric: " + metricName);
                }
                selectedMetrics.put(metricName, value);
            }

            long fingerprintStartNs = TimingTrace.nowNs();
            String fingerprint = fingerprintBuilder.buildFingerprint(request);
            timing.markFromStart("fingerprint_ms", fingerprintStartNs);

            long artifactStoreStartNs = TimingTrace.nowNs();
            EvaluationResult result = artifactStore.store(request, selectedMetrics, discovered.getPnml(), fingerprint);
            timing.markFromStart("store_artifact_ms", artifactStoreStartNs);
            return result;
        } catch (Exception error) {
            failed = true;
            failureType = error.getClass().getSimpleName();
            throw error;
        } finally {
            long totalMs = TimingTrace.elapsedMs(evaluationStartNs);
            timing.logSummary(
                totalMs,
                failed,
                failureType,
                experimentId,
                minerKey,
                minerVariant,
                preprocessingKey,
                requestedMetrics
            );
        }
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

    private PluginContext createContext() {
        CLIContext global = new CLIContext();
        return new CLIPluginContext(global, "minersweeper");
    }

    private Map<String, MinerDiscoverer> createMiners() {
        DiscoveryArtifactFactory artifactFactory = new DiscoveryArtifactFactory(new PmnlExporter());
        Map<String, MinerDiscoverer> discoverers = new LinkedHashMap<String, MinerDiscoverer>();
        register(discoverers, new AlphaMinerDiscoverer(artifactFactory));
        register(discoverers, new InductiveMinerDiscoverer(artifactFactory));
        register(discoverers, new HeuristicsMinerDiscoverer(artifactFactory));
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
}
