package com.minersweeper.javaservice.evaluation.discovery.miners;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifact;
import com.minersweeper.javaservice.evaluation.discovery.DiscoveryArtifactFactory;
import com.minersweeper.javaservice.evaluation.discovery.MinerDiscoverer;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfo;
import org.deckfour.xes.info.XLogInfoFactory;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.plugins.ilpminer.ILPMiner;
import org.processmining.plugins.ilpminer.ILPMinerSettings;
import org.processmining.plugins.ilpminer.ILPMinerSettings.SolverSetting;
import org.processmining.plugins.ilpminer.ILPMinerSettings.SolverType;
import org.processmining.plugins.ilpminer.templates.PetriNetILPModelSettings;
import org.processmining.plugins.ilpminer.templates.PetriNetILPModelSettings.SearchType;
import org.processmining.plugins.ilpminer.templates.PetriNetVariableFitnessILPModelSettings;
import org.processmining.plugins.ilpminer.templates.javailp.PetriNetILPModel;
import org.processmining.plugins.ilpminer.templates.javailp.PetriNetVariableFitnessILPModel;

public final class IlpMinerDiscoverer implements MinerDiscoverer {
    private final DiscoveryArtifactFactory artifactFactory;

    public IlpMinerDiscoverer(DiscoveryArtifactFactory artifactFactory) {
        this.artifactFactory = artifactFactory;
    }

    @Override
    public String key() {
        return "ilp";
    }

    @Override
    public DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception {
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
        return artifactFactory.fromResultArray(context, result);
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
}
