package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import java.util.Map;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.hybridilpminer.parameters.DiscoveryStrategy;
import org.processmining.hybridilpminer.parameters.DiscoveryStrategyType;
import org.processmining.hybridilpminer.parameters.LPFilter;
import org.processmining.hybridilpminer.parameters.LPFilterType;
import org.processmining.hybridilpminer.parameters.LPObjectiveType;
import org.processmining.hybridilpminer.parameters.LPVariableType;
import org.processmining.hybridilpminer.parameters.XLogHybridILPMinerParametersImpl;
import org.processmining.hybridilpminer.plugins.HybridILPMinerPlugin;

public final class HybridIlpMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;

    public HybridIlpMinerDiscoverer(DiscoveryArtifactFactory artifactFactory) {
        this.artifactFactory = artifactFactory;
    }

    @Override
    public String key() {
        return "hybrid_ilp";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
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
        return artifactFactory.fromResultArray(context, result);
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
}
