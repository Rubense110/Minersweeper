package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.heuristics.HeuristicsNet;
import org.processmining.plugins.heuristicsnet.miner.heuristics.converter.HeuristicsNetToPetriNetConverter;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.FlexibleHeuristicsMinerPlugin;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.HeuristicsMiner;
import org.processmining.plugins.heuristicsnet.miner.heuristics.miner.settings.HeuristicsMinerSettings;

public final class HeuristicsMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;

    public HeuristicsMinerDiscoverer(DiscoveryArtifactFactory artifactFactory) {
        this.artifactFactory = artifactFactory;
    }

    @Override
    public String key() {
        return "heuristics";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
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
        return artifactFactory.fromResultArray(context, result);
    }
}
