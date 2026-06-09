package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;

public class TokenReplayComputation {
    private final XLog log;
    private final TokenReplayEngine engine;
    private final TimingTrace timing;

    private TokenReplayResult result;

    public TokenReplayComputation(
        XLog log,
        Petrinet net,
        Marking initialMarking,
        Marking finalMarking,
        XEventClassifier classifier,
        TransEvClassMapping mapping,
        TimingTrace timing
    ) {
        this(log, new TokenReplayEngine(net, initialMarking, finalMarking, classifier, mapping), timing);
    }

    public TokenReplayComputation(XLog log, TokenReplayEngine engine, TimingTrace timing) {
        this.log = log;
        this.engine = engine;
        this.timing = timing;
    }

    public synchronized TokenReplayResult compute() {
        if (result != null) {
            return result;
        }
        long tokenReplayStartNs = TimingTrace.nowNs();

        Map<List<String>, Integer> variants = engine.variantsByActivitySequence(log);
        Map<Transition, Integer> activations = new LinkedHashMap<Transition, Integer>();
        TokenReplayEngine.Counts totals = new TokenReplayEngine.Counts();
        long fitTraces = 0L;

        for (Map.Entry<List<String>, Integer> variant : variants.entrySet()) {
            TokenReplayEngine.TraceReplay traceReplay = engine.replayFitnessTrace(variant.getKey());
            int multiplicity = variant.getValue().intValue();
            totals.add(traceReplay.counts(), multiplicity);
            if (traceReplay.fit()) {
                fitTraces += multiplicity;
            }
            for (Map.Entry<Transition, Integer> activation : traceReplay.activations().entrySet()) {
                TokenReplayEngine.addActivation(
                    activations,
                    activation.getKey(),
                    activation.getValue().intValue() * multiplicity
                );
            }
        }

        result = new TokenReplayResult(
            totals.missing,
            totals.consumed,
            totals.remaining,
            totals.produced,
            log == null ? 0L : (long) log.size(),
            fitTraces,
            activations
        );
        if (timing != null) {
            timing.markFromStart("token_replay_ms", tokenReplayStartNs);
        }
        return result;
    }
}
