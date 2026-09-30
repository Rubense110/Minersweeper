package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.util.LinkedHashMap;
import java.util.ArrayList;
import java.util.Collections;
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
    private final List<TokenReplayEngine> finalEngines;
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
        this.finalEngines = Collections.singletonList(engine);
        this.timing = timing;
    }

    public TokenReplayComputation(
        XLog log,
        Petrinet net,
        Marking initialMarking,
        List<Marking> finalMarkings,
        XEventClassifier classifier,
        TransEvClassMapping mapping,
        TimingTrace timing
    ) {
        this(log, net, initialMarking, finalMarkings, classifier, mapping, timing, new CompiledReplayNet(net));
    }

    public TokenReplayComputation(XLog log, Petrinet net, Marking initialMarking,
        List<Marking> finalMarkings, XEventClassifier classifier, TransEvClassMapping mapping,
        TimingTrace timing, CompiledReplayNet compiled) {
        if (finalMarkings == null || finalMarkings.isEmpty()) {
            throw new IllegalArgumentException("at least one final marking is required");
        }
        this.log = log;
        this.finalEngines = new ArrayList<TokenReplayEngine>();
        for (Marking fin : finalMarkings) {
            this.finalEngines.add(new TokenReplayEngine(net, initialMarking, fin, classifier, mapping, compiled));
        }
        this.engine = this.finalEngines.get(0);
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
            ExecutionChecks.check();
            TokenReplayEngine.TraceReplay traceReplay = bestReplay(variant.getKey());
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

    private TokenReplayEngine.TraceReplay bestReplay(List<String> activities) {
        TokenReplayEngine.TraceReplay best = null;
        for (TokenReplayEngine candidateEngine : finalEngines) {
            TokenReplayEngine.TraceReplay candidate = candidateEngine.replayFitnessTrace(activities);
            if (best == null || replayPenalty(candidate) < replayPenalty(best)
                || (replayPenalty(candidate) == replayPenalty(best) && candidate.fit() && !best.fit())) {
                best = candidate;
            }
        }
        return best;
    }

    private long replayPenalty(TokenReplayEngine.TraceReplay replay) {
        return replay.counts().missing + replay.counts().remaining;
    }
}
