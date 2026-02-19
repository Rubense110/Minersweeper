package com.minersweeper.javaservice.evaluation.conformance;

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

public class ConformanceComputation {
    private final PluginContext context;
    private final XLog log;
    private final Petrinet net;
    private final Marking initialMarking;
    private final Marking finalMarking;

    private XEventClassifier classifier;
    private XEventClasses eventClasses;
    private XEventClass dummyEventClass;
    private TransEvClassMapping mapping;
    private PNRepResult replayResult;
    private AlignmentPrecGenRes alignment;

    public ConformanceComputation(
        PluginContext context,
        XLog log,
        Petrinet net,
        Marking initialMarking,
        Marking finalMarking
    ) {
        this.context = context;
        this.log = log;
        this.net = net;
        this.initialMarking = initialMarking;
        this.finalMarking = finalMarking;
    }

    public Petrinet getNet() {
        return net;
    }

    public synchronized TransEvClassMapping getMapping() {
        if (mapping != null) {
            return mapping;
        }

        TransEvClassMapping resolvedMapping = new TransEvClassMapping(getClassifier(), getDummyEventClass());
        for (Transition transition : net.getTransitions()) {
            XEventClass targetClass = null;
            if (!transition.isInvisible()) {
                targetClass = getEventClasses().getByIdentity(transition.getLabel());
                if (targetClass == null) {
                    targetClass = getEventClasses().getByIdentity(transition.getLabel() + "+complete");
                }
            }
            resolvedMapping.put(transition, targetClass != null ? targetClass : getDummyEventClass());
        }

        mapping = resolvedMapping;
        return mapping;
    }

    public synchronized PNRepResult getReplayResult() throws Exception {
        if (replayResult != null) {
            return replayResult;
        }

        CostBasedCompleteParam replayParam = new CostBasedCompleteParam(
            getEventClasses().getClasses(),
            getDummyEventClass(),
            net.getTransitions(),
            1,
            1
        );
        replayParam.setInitialMarking(initialMarking);
        replayParam.setFinalMarkings(finalMarking);
        replayParam.setCreateConn(false);
        replayParam.setGUIMode(false);
        replayParam.setNumThreads(1);

        PNLogReplayer replayer = new PNLogReplayer();
        PetrinetReplayerWithILP replayAlgorithm = new PetrinetReplayerWithILP();
        replayResult = replayer.replayLog(context, net, log, getMapping(), replayAlgorithm, replayParam);
        return replayResult;
    }

    public synchronized AlignmentPrecGenRes getAlignment() throws Exception {
        if (alignment != null) {
            return alignment;
        }

        AlignmentPrecGen alignmentPrecGen = new AlignmentPrecGen();
        alignment = alignmentPrecGen.measureConformanceAssumingCorrectAlignment(
            context,
            getMapping(),
            getReplayResult(),
            net,
            initialMarking,
            false
        );
        return alignment;
    }

    private XEventClassifier getClassifier() {
        if (classifier == null) {
            classifier = new XEventNameClassifier();
        }
        return classifier;
    }

    private XEventClasses getEventClasses() {
        if (eventClasses == null) {
            XLogInfo logInfo = XLogInfoFactory.createLogInfo(log, getClassifier());
            eventClasses = logInfo.getEventClasses();
        }
        return eventClasses;
    }

    private XEventClass getDummyEventClass() {
        if (dummyEventClass == null) {
            dummyEventClass = new XEventClass("DUMMY", getEventClasses().size() + 1);
        }
        return dummyEventClass;
    }
}
