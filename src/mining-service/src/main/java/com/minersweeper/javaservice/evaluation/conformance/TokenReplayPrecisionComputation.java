package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.app.logging.TimingTrace;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;

public class TokenReplayPrecisionComputation {
    private final XLog log;
    private final TokenReplayEngine engine;
    private final TimingTrace timing;

    private TokenReplayPrecisionResult result;

    public TokenReplayPrecisionComputation(XLog log, TokenReplayEngine engine, TimingTrace timing) {
        this.log = log;
        this.engine = engine;
        this.timing = timing;
    }

    public synchronized TokenReplayPrecisionResult compute() {
        if (result != null) {
            return result;
        }
        long precisionStartNs = TimingTrace.nowNs();

        Map<List<String>, PrefixStats> prefixes = collectPrefixes();
        long prefixCount = 0L;
        long replayedPrefixCount = 0L;
        long activatedTransitions = 0L;
        long escapingEdges = 0L;

        for (Map.Entry<List<String>, PrefixStats> entry : prefixes.entrySet()) {
            List<String> prefix = entry.getKey();
            PrefixStats stats = entry.getValue();
            prefixCount += stats.count;

            TokenReplayEngine.TraceReplay replay = engine.replayPrefix(prefix);
            if (!replay.fit()) {
                continue;
            }
            replayedPrefixCount += stats.count;

            Set<String> activated = normalizeActivities(engine.visibleActivitiesEventuallyEnabled(replay.marking()));
            if (activated.isEmpty()) {
                continue;
            }
            Set<String> reflected = normalizeActivities(stats.reflectedTasks);

            long escaping = 0L;
            for (String activity : activated) {
                if (!reflected.contains(activity)) {
                    escaping++;
                }
            }

            activatedTransitions += stats.count * (long) activated.size();
            escapingEdges += stats.count * escaping;
        }

        result = new TokenReplayPrecisionResult(
            prefixCount,
            replayedPrefixCount,
            activatedTransitions,
            escapingEdges
        );
        if (timing != null) {
            timing.markFromStart("token_precision_ms", precisionStartNs);
        }
        return result;
    }

    private Map<List<String>, PrefixStats> collectPrefixes() {
        Map<List<String>, PrefixStats> prefixes = new LinkedHashMap<List<String>, PrefixStats>();
        if (log == null) {
            return prefixes;
        }
        for (XTrace trace : log) {
            List<String> activities = engine.activitiesOf(trace);
            for (int prefixLength = 0; prefixLength <= activities.size(); prefixLength++) {
                List<String> prefix = immutablePrefix(activities, prefixLength);
                PrefixStats stats = prefixes.get(prefix);
                if (stats == null) {
                    stats = new PrefixStats();
                    prefixes.put(prefix, stats);
                }
                stats.count++;
                if (prefixLength < activities.size()) {
                    stats.reflectedTasks.add(activities.get(prefixLength));
                }
            }
        }
        return prefixes;
    }

    private List<String> immutablePrefix(List<String> activities, int prefixLength) {
        if (prefixLength == 0) {
            return Collections.emptyList();
        }
        return Collections.unmodifiableList(new ArrayList<String>(activities.subList(0, prefixLength)));
    }

    private Set<String> normalizeActivities(Set<String> activities) {
        Set<String> normalized = new LinkedHashSet<String>();
        for (String activity : activities) {
            if (activity == null) {
                continue;
            }
            normalized.add(normalizeActivity(activity));
        }
        return normalized;
    }

    private String normalizeActivity(String activity) {
        if (activity.endsWith("+complete")) {
            return activity.substring(0, activity.length() - "+complete".length());
        }
        return activity;
    }

    private static class PrefixStats {
        long count;
        final Set<String> reflectedTasks = new LinkedHashSet<String>();
    }
}
