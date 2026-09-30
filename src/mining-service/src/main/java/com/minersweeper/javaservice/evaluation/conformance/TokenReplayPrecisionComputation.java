package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.Set;
import org.deckfour.xes.model.XLog;
import org.processmining.models.semantics.petrinet.Marking;

public class TokenReplayPrecisionComputation {
    private final XLog log;
    private final TokenReplayEngine engine;
    private final TimingTrace timing;
    private TokenReplayPrecisionResult result;

    public TokenReplayPrecisionComputation(XLog log, TokenReplayEngine engine, TimingTrace timing) {
        this.log = log; this.engine = engine; this.timing = timing;
    }

    public synchronized TokenReplayPrecisionResult compute() {
        if (result != null) return result;
        long start = TimingTrace.nowNs();
        LogReplayStatistics statistics = engine.statistics(log);
        long replayed = 0L, activatedCount = 0L, escapingCount = 0L, replayedEdges = 0L;
        ArrayDeque<Frame> stack = new ArrayDeque<Frame>();
        stack.push(new Frame(0, engine.initialPrefixMarking(), statistics));
        while (!stack.isEmpty()) {
            ExecutionChecks.check();
            Frame frame = stack.peek();
            if (!frame.counted) {
                frame.counted = true;
                replayed += statistics.nodeCounts[frame.node];
                Set<String> activated = normalize(engine.visibleActivitiesEventuallyEnabled(frame.marking));
                if (!activated.isEmpty()) {
                    Set<String> reflected = new LinkedHashSet<String>();
                    for (int edge = statistics.childStarts[frame.node]; edge < statistics.childStarts[frame.node + 1]; edge++) {
                        reflected.add(normalize(statistics.activities.get(statistics.nodeActivities[statistics.childNodes[edge]])));
                    }
                    long escaping = 0L;
                    for (String activity : activated) if (!reflected.contains(activity)) escaping++;
                    activatedCount += statistics.nodeCounts[frame.node] * activated.size();
                    escapingCount += statistics.nodeCounts[frame.node] * escaping;
                }
            }
            if (frame.nextChild >= statistics.childStarts[frame.node + 1]) { stack.pop(); continue; }
            int child = statistics.childNodes[frame.nextChild++];
            TokenReplayEngine.TraceReplay step = engine.advancePrefix(
                frame.marking, statistics.activities.get(statistics.nodeActivities[child])
            );
            replayedEdges++;
            // An unfit prefix makes all descendants unfit under the existing policy.
            if (step.fit()) stack.push(new Frame(child, step.marking(), statistics));
        }
        result = new TokenReplayPrecisionResult(statistics.prefixCount, replayed, activatedCount, escapingCount);
        if (timing != null) {
            timing.putField("token_prefix_nodes", Integer.toString(statistics.prefixNodes));
            timing.putField("token_prefix_edges_replayed", Long.toString(replayedEdges));
            timing.markFromStart("token_precision_ms", start);
        }
        return result;
    }

    private static Set<String> normalize(Set<String> activities) {
        Set<String> normalized = new LinkedHashSet<String>();
        for (String activity : activities) if (activity != null) normalized.add(normalize(activity));
        return normalized;
    }
    private static String normalize(String activity) {
        return activity.endsWith("+complete")
            ? activity.substring(0, activity.length() - "+complete".length()) : activity;
    }
    private static final class Frame {
        final int node;
        final Marking marking;
        int nextChild;
        boolean counted;
        Frame(int node, Marking marking, LogReplayStatistics statistics) {
            this.node = node; this.marking = marking; nextChild = statistics.childStarts[node];
        }
    }
}
