package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
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
import org.processmining.plugins.etconformance.ETCAlgorithm;
import org.processmining.plugins.etconformance.ETCResults;
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
    private final ConformanceMode conformanceMode;
    private final TimingTrace timing;

    private XEventClassifier classifier;
    private XEventClasses eventClasses;
    private XEventClass dummyEventClass;
    private TransEvClassMapping mapping;
    private PNRepResult replayResult;
    private AlignmentPrecGenRes alignment;
    private Double replayPrecision;

    public ConformanceComputation(
        PluginContext context,
        XLog log,
        Petrinet net,
        Marking initialMarking,
        Marking finalMarking,
        ConformanceMode conformanceMode,
        TimingTrace timing
    ) {
        this.context = context;
        this.log = log;
        this.net = net;
        this.initialMarking = initialMarking;
        this.finalMarking = finalMarking;
        this.conformanceMode = conformanceMode == null ? ConformanceMode.ALIGNMENT : conformanceMode;
        this.timing = timing;
    }

    public Petrinet getNet() {
        return net;
    }

    public synchronized TransEvClassMapping getMapping() {
        if (mapping != null) {
            return mapping;
        }
        long mappingStartNs = TimingTrace.nowNs();

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
        if (timing != null) {
            timing.markFromStart("mapping_ms", mappingStartNs);
        }
        return mapping;
    }

    public synchronized PNRepResult getReplayResult() throws Exception {
        if (replayResult != null) {
            return replayResult;
        }
        long replayStartNs = TimingTrace.nowNs();

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
        if (timing != null) {
            timing.markFromStart("replay_ms", replayStartNs);
        }
        return replayResult;
    }

    public synchronized double getFitness() throws Exception {
        Map<String, Object> info = getReplayResult().getInfo();
        return MetricUtils.toDouble(info.get(PNRepResult.TRACEFITNESS), 0.0);
    }

    public synchronized double getPrecision() throws Exception {
        if (conformanceMode.isAlignment()) {
            return getAlignment().getPrecision();
        }
        return getReplayPrecision();
    }

    public synchronized double getGeneralisation() throws Exception {
        if (!conformanceMode.isAlignment()) {
            throw new IllegalArgumentException(
                "metric generalisation is not available for conformance_mode=" + conformanceMode.key()
            );
        }
        return getAlignment().getGeneralization();
    }

    public synchronized AlignmentPrecGenRes getAlignment() throws Exception {
        if (alignment != null) {
            return alignment;
        }
        long alignmentStartNs = TimingTrace.nowNs();

        AlignmentPrecGen alignmentPrecGen = new AlignmentPrecGen();
        alignment = alignmentPrecGen.measureConformanceAssumingCorrectAlignment(
            context,
            getMapping(),
            getReplayResult(),
            net,
            initialMarking,
            false
        );
        if (timing != null) {
            timing.markFromStart("alignment_ms", alignmentStartNs);
        }
        return alignment;
    }

    private synchronized double getReplayPrecision() throws Exception {
        if (replayPrecision != null) {
            return replayPrecision.doubleValue();
        }
        long replayPrecisionStartNs = TimingTrace.nowNs();

        ETCResults results = new ETCResults();
        ETCAlgorithm.exec(context, log, net, initialMarking, getMapping(), results);
        replayPrecision = Double.valueOf(results.getEtcp());

        if (timing != null) {
            timing.markFromStart("replay_precision_ms", replayPrecisionStartNs);
        }
        return replayPrecision.doubleValue();
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
