package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.lang.ref.WeakReference;
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;

/** Immutable statistics of a read-only original log, shared by candidate nets. */
public final class LogReplayStatistics {
    private static final int MAX_ENTRIES = 4;
    private static final long MAX_CACHE_BYTES = 64L * 1024L * 1024L;
    // Identity lookup avoids XLog's mutable and expensive List.hashCode().
    // Values never refer back to the log, so these weak references can expire.
    private static final List<CacheEntry> CACHE = new ArrayList<CacheEntry>();
    final int[] childStarts;
    final int[] childNodes;
    final int[] nodeActivities;
    final long[] nodeCounts;
    final List<String> activities;
    final XEventClasses eventClasses;
    final Map<List<String>, Integer> variants;
    final long prefixCount;
    final long estimatedBytes;
    final int prefixNodes;

    private LogReplayStatistics(XLog log, XEventClassifier classifier) {
        PrefixNode root = new PrefixNode(-1);
        eventClasses = new XEventClasses(classifier);
        Map<String, Integer> symbols = new LinkedHashMap<String, Integer>();
        Map<IntSequence, Integer> counts = new LinkedHashMap<IntSequence, Integer>();
        if (log != null) for (XTrace trace : log) {
            ExecutionChecks.check();
            int[] sequence = new int[trace.size()];
            int size = 0;
            for (XEvent event : trace) {
                ExecutionChecks.check();
                String activity = classifier.getClassIdentity(event);
                if (activity == null) continue;
                eventClasses.register(activity);
                Integer symbol = symbols.get(activity);
                if (symbol == null) { symbol = symbols.size(); symbols.put(activity, symbol); }
                sequence[size++] = symbol.intValue();
            }
            IntSequence key = new IntSequence(size == sequence.length ? sequence : Arrays.copyOf(sequence, size));
            Integer previous = counts.get(key);
            counts.put(key, previous == null ? 1 : previous + 1);
        }
        eventClasses.harmonizeIndices();
        activities = Collections.unmodifiableList(new ArrayList<String>(symbols.keySet()));
        Map<List<String>, Integer> weighted = new LinkedHashMap<List<String>, Integer>();
        long prefixes = 0L;
        long bytes = 128L + 80L * activities.size();
        int nodes = 1;
        for (Map.Entry<IntSequence, Integer> entry : counts.entrySet()) {
            ExecutionChecks.check();
            final int[] sequence = entry.getKey().ids;
            weighted.put(Collections.unmodifiableList(new AbstractList<String>() {
                @Override public String get(int index) { return activities.get(sequence[index]); }
                @Override public int size() { return sequence.length; }
            }), entry.getValue());
            int multiplicity = entry.getValue();
            prefixes += ((long) sequence.length + 1L) * multiplicity;
            bytes += 112L + 4L * sequence.length;
            PrefixNode node = root;
            node.count += multiplicity;
            for (int symbol : sequence) {
                ExecutionChecks.check();
                PrefixNode child = node.children.get(symbol);
                if (child == null) {
                    child = new PrefixNode(symbol); node.children.put(symbol, child); nodes++;
                }
                child.count += multiplicity;
                node = child;
            }
        }
        // Flatten the builder into four contiguous primitive arrays. Most trie
        // nodes have one child; retaining a LinkedHashMap per node is wasteful.
        childStarts = new int[nodes + 1]; childNodes = new int[nodes - 1];
        nodeActivities = new int[nodes]; nodeCounts = new long[nodes];
        List<PrefixNode> ordered = new ArrayList<PrefixNode>(nodes);
        ordered.add(root);
        int edge = 0;
        for (int index = 0; index < nodes; index++) {
            ExecutionChecks.check();
            PrefixNode node = ordered.get(index);
            nodeActivities[index] = node.activity; nodeCounts[index] = node.count;
            childStarts[index] = edge;
            for (PrefixNode child : node.children.values()) {
                ExecutionChecks.check();
                childNodes[edge++] = ordered.size(); ordered.add(child);
            }
        }
        childStarts[nodes] = edge;
        variants = Collections.unmodifiableMap(weighted);
        prefixCount = prefixes; prefixNodes = nodes; estimatedBytes = bytes + 24L * nodes;
    }

    public XEventClasses eventClasses() { return eventClasses; }

    public static synchronized LogReplayStatistics forLog(XLog log, XEventClassifier classifier) {
        ExecutionChecks.check();
        String key = classifier.getClass().getName() + "|" + classifier.name()
            + "|" + Arrays.toString(classifier.getDefiningAttributeKeys());
        for (Iterator<CacheEntry> it = CACHE.iterator(); it.hasNext();) {
            ExecutionChecks.check();
            CacheEntry entry = it.next();
            XLog cached = entry.log.get();
            if (cached == null || cached.size() != entry.traceCount) { it.remove(); continue; }
            if (cached == log && entry.classifier.equals(key)) return entry.statistics;
        }
        LogReplayStatistics built = new LogReplayStatistics(log, classifier);
        // Only cache standard attribute-based classifiers. Custom classifiers can
        // have private state not described by their name and attribute keys.
        boolean standard = classifier.getClass().getName().startsWith("org.deckfour.xes.classification.");
        if (log != null && standard && built.estimatedBytes <= MAX_CACHE_BYTES) {
            long bytes = built.estimatedBytes;
            for (CacheEntry entry : CACHE) bytes += entry.statistics.estimatedBytes;
            while (!CACHE.isEmpty() && (CACHE.size() >= MAX_ENTRIES || bytes > MAX_CACHE_BYTES)) {
                bytes -= CACHE.remove(0).statistics.estimatedBytes;
            }
            CACHE.add(new CacheEntry(log, key, built));
        }
        return built;
    }

    public static synchronized void evict(XLog log) {
        CACHE.removeIf(entry -> entry.log.get() == null || entry.log.get() == log);
    }
    public Map<List<String>, Integer> variants() { return variants; }
    public int prefixNodeCount() { return prefixNodes; }

    static final class PrefixNode {
        final int activity;
        long count;
        final Map<Integer, PrefixNode> children = new LinkedHashMap<Integer, PrefixNode>();
        PrefixNode(int activity) { this.activity = activity; }
    }
    private static final class IntSequence {
        final int[] ids;
        final int hash;
        IntSequence(int[] ids) { this.ids = ids; hash = Arrays.hashCode(ids); }
        @Override public int hashCode() { return hash; }
        @Override public boolean equals(Object other) {
            return other instanceof IntSequence && Arrays.equals(ids, ((IntSequence) other).ids);
        }
    }
    private static final class CacheEntry {
        final WeakReference<XLog> log;
        final int traceCount;
        final String classifier;
        final LogReplayStatistics statistics;
        CacheEntry(XLog log, String classifier, LogReplayStatistics statistics) {
            this.log = new WeakReference<XLog>(log); traceCount = log.size();
            this.classifier = classifier; this.statistics = statistics;
        }
    }
}
