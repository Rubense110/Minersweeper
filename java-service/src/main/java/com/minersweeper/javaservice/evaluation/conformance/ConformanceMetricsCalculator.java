package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.conformance.metrics.Fitness;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Generalisation;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Precision;
import com.minersweeper.javaservice.evaluation.conformance.metrics.Simplicity;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import java.util.LinkedHashMap;
import java.util.Map;
import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfo;
import org.deckfour.xes.info.XLogInfoFactory;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.astar.petrinet.PetrinetReplayerWithILP;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;
import org.processmining.plugins.petrinet.replayer.PNLogReplayer;
import org.processmining.plugins.petrinet.replayer.algorithms.costbasedcomplete.CostBasedCompleteParam;
import org.processmining.plugins.petrinet.replayresult.PNRepResult;
import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGen;
import org.processmining.plugins.pnalignanalysis.conformance.AlignmentPrecGenRes;

public class ConformanceMetricsCalculator {
    private static final String METRIC_GENERALISATION = "generalisation";

    public Map<String, Double> compute(
        PluginContext context,
        XLog log,
        Petrinet net,
        Marking initial,
        Marking fin
    ) throws Exception {
        XEventClassifier classifier = new XEventNameClassifier();
        XLogInfo logInfo = XLogInfoFactory.createLogInfo(log, classifier);
        XEventClasses eventClasses = logInfo.getEventClasses();
        XEventClass dummy = new XEventClass("DUMMY", eventClasses.size() + 1);

        TransEvClassMapping mapping = new TransEvClassMapping(classifier, dummy);
        for (Transition transition : net.getTransitions()) {
            XEventClass targetClass = null;
            if (!transition.isInvisible()) {
                targetClass = eventClasses.getByIdentity(transition.getLabel());
                if (targetClass == null) {
                    targetClass = eventClasses.getByIdentity(transition.getLabel() + "+complete");
                }
            }
            mapping.put(transition, targetClass != null ? targetClass : dummy);
        }

        CostBasedCompleteParam replayParam = new CostBasedCompleteParam(
            eventClasses.getClasses(),
            dummy,
            net.getTransitions(),
            1,
            1
        );
        replayParam.setInitialMarking(initial);
        replayParam.setFinalMarkings(fin);
        replayParam.setCreateConn(false);
        replayParam.setGUIMode(false);
        replayParam.setNumThreads(1);

        PNLogReplayer replayer = new PNLogReplayer();
        PetrinetReplayerWithILP replayAlgorithm = new PetrinetReplayerWithILP();
        PNRepResult replayResult = replayer.replayLog(context, net, log, mapping, replayAlgorithm, replayParam);

        AlignmentPrecGen alignmentPrecGen = new AlignmentPrecGen();
        AlignmentPrecGenRes alignment = alignmentPrecGen.measureConformanceAssumingCorrectAlignment(
            context,
            mapping,
            replayResult,
            net,
            initial,
            false
        );

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        metrics.put("fitness", MetricUtils.clamp01(Fitness.compute(replayResult)));
        metrics.put("precision", MetricUtils.clamp01(Precision.compute(alignment)));
        metrics.put(METRIC_GENERALISATION, MetricUtils.clamp01(Generalisation.compute(alignment)));
        metrics.put("simplicity", MetricUtils.clamp01(Simplicity.computeStructuralSimplicity(net)));
        return metrics;
    }
}
