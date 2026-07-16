package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.ExperimentExecutionRegistry;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.acceptingpetrinet.models.AcceptingPetriNet;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.framework.packages.PackageManager.Canceller;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.plugins.InductiveMiner.mining.logs.LifeCycleClassifier;
import org.processmining.plugins.InductiveMiner.mining.logs.XLifeCycleClassifier;
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

public final class InductiveMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;
    private final ExperimentExecutionRegistry executionRegistry;

    public InductiveMinerDiscoverer(
        DiscoveryArtifactFactory artifactFactory,
        ExperimentExecutionRegistry executionRegistry
    ) {
        this.artifactFactory = artifactFactory;
        this.executionRegistry = executionRegistry;
    }

    @Override
    public String key() {
        return "inductive";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
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
                return executionRegistry != null
                    && executionRegistry.isCancellationRequested(request.experiment_id, request.request_id);
            }
        };

        AcceptingPetriNet apn = InductiveMinerPlugin.minePetriNet(imLog, params, canceller);
        // Keep parity with previous behavior: export PNML using a fresh CLI context.
        return artifactFactory.fromResultArray(createContext(), new Object[] { apn });
    }

    private PluginContext createContext() {
        CLIContext global = new CLIContext();
        return new CLIPluginContext(global, "minersweeper");
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
}
