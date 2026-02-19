package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.alphaminer.parameters.AlphaRobustMinerParameters;
import org.processmining.alphaminer.parameters.AlphaVersion;
import org.processmining.alphaminer.plugins.AlphaMinerPlugin;
import org.processmining.framework.plugin.PluginContext;

public final class AlphaMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;

    public AlphaMinerDiscoverer(DiscoveryArtifactFactory artifactFactory) {
        this.artifactFactory = artifactFactory;
    }

    @Override
    public String key() {
        return "alpha";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
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
        return artifactFactory.fromResultArray(context, result);
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
}
