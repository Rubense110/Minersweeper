package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import org.processmining.acceptingpetrinet.models.AcceptingPetriNet;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.alphaminer.algorithms.AlphaClassicMinerImpl;
import org.processmining.alphaminer.algorithms.AlphaMiner;
import org.processmining.alphaminer.algorithms.AlphaMinerFactory;
import org.processmining.alphaminer.algorithms.AlphaRobustMinerImpl;
import org.processmining.alphaminer.parameters.AlphaMinerParameters;
import org.processmining.alphaminer.parameters.AlphaRobustMinerParameters;
import org.processmining.alphaminer.parameters.AlphaVersion;
import org.processmining.alphaminer.plugins.AlphaMinerPlugin;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.framework.util.Pair;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.semantics.petrinet.Marking;

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
        if (AlphaVersion.SHARP.equals(version) || AlphaVersion.DOLLAR.equals(version)) {
            // Retired catalog variants keep their existing direct-service behavior.
            return artifactFactory.fromResultArray(
                context, AlphaMinerPlugin.apply(context, log, new XEventNameClassifier(), version)
            );
        }
        AlphaMinerParameters parameters;
        if (AlphaVersion.ROBUST.equals(version)) {
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
            parameters = robustParams;
        } else {
            parameters = new AlphaMinerParameters(version);
        }

        AlphaMiner<?, ?, ?> miner = AlphaMinerFactory.createAlphaMiner(
            context, log, new XEventNameClassifier(), parameters
        );
        if (AlphaVersion.CLASSIC.equals(version)) {
            AcceptingPetriNet accepting = ((AlphaClassicMinerImpl<?, ?, ?>) miner).runAccPN();
            return artifactFactory.fromResultArray(context, new Object[] {accepting});
        }
        if (AlphaVersion.ROBUST.equals(version)) {
            AcceptingPetriNet accepting = ((AlphaRobustMinerImpl<?, ?, ?>) miner).runAccPN();
            return artifactFactory.fromResultArray(context, new Object[] {accepting});
        }
        if (AlphaVersion.PLUS.equals(version) || AlphaVersion.PLUS_PLUS.equals(version)) {
            Pair<Petrinet, Marking> discovered = miner.run();
            Petrinet net = discovered.getFirst();
            Marking finalMarking = finalMarkingFromAlphaEndPlace(net);
            return artifactFactory.fromResultArray(
                context, new Object[] {net, discovered.getSecond(), finalMarking}
            );
        }
        throw new IllegalArgumentException("Unsupported Alpha version: " + version);
    }

    private Marking finalMarkingFromAlphaEndPlace(Petrinet net) {
        Place end = null;
        for (Place place : net.getPlaces()) {
            if (!"End".equals(place.getLabel())) {
                continue;
            }
            if (end != null) {
                throw new IllegalStateException("Alpha+/++ produced multiple End places");
            }
            end = place;
        }
        if (end == null || net.getInEdges(end).isEmpty() || !net.getOutEdges(end).isEmpty()) {
            throw new IllegalStateException("Alpha+/++ has no unambiguous terminal End place");
        }
        Marking finalMarking = new Marking();
        finalMarking.add(end);
        return finalMarking;
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
