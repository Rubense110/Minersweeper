package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.raffaeleconforti.conversion.bpmn.BPMNToPetriNetConverter;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.bpmn.BPMNDiagram;
import processmining.splitminer.SplitMiner;
import processmining.splitminer.ui.dfgp.DFGPUIResult.FilterType;
import processmining.splitminer.ui.miner.SplitMinerUIResult.StructuringTime;

public final class SplitMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;

    public SplitMinerDiscoverer(DiscoveryArtifactFactory artifactFactory) {
        this.artifactFactory = artifactFactory;
    }

    @Override
    public String key() {
        return "split";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
        double eta = ParameterReader.doubleParam(request.pipeline.miner.parameters, "eta", 0.5d);
        double epsilon = ParameterReader.doubleParam(request.pipeline.miner.parameters, "epsilon", 0.5d);

        SplitMiner splitMiner = new SplitMiner();
        BPMNDiagram bpmn = splitMiner.mineBPMNModel(
            log,
            new XEventNameClassifier(),
            eta,
            epsilon,
            FilterType.FWG,
            false,
            false,
            false,
            StructuringTime.NONE
        );
        if (bpmn == null) {
            throw new IllegalStateException("Split Miner returned no BPMN model");
        }

        Object[] result = BPMNToPetriNetConverter.convert(bpmn);
        return artifactFactory.fromResultArray(context, result);
    }
}
