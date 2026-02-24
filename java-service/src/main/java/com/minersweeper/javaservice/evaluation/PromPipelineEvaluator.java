package com.minersweeper.javaservice.evaluation;

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
        Path logFile = logLoader.resolveLogPath(request.log_path);
        XLog log = logLoader.loadLog(logFile.toFile());
        PluginContext context = createContext();

        DiscoveryArtifact discovered = discoverModel(context, log, request);
        Map<String, Double> canonicalMetrics = conformanceMetricsCalculator.compute(
            context,
            log,
            discovered.getNet(),
            discovered.getInitialMarking(),
            discovered.getFinalMarking(),
            request.metrics
        );

        Map<String, Double> selectedMetrics = new LinkedHashMap<String, Double>();
        for (String metricName : request.metrics) {
            Double value = canonicalMetrics.get(metricName);
            if (value == null) {
                throw new IllegalArgumentException("unsupported metric: " + metricName);
            }
            selectedMetrics.put(metricName, value);
        }

        String fingerprint = fingerprintBuilder.buildFingerprint(request);
        return artifactStore.store(request, selectedMetrics, discovered.getPnml(), fingerprint);
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
}
