package com.minersweeper.javaservice.evaluation.preprocessing;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.factory.XFactoryRegistry;
import org.deckfour.xes.model.XAttribute;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;

/** Name-based variants, preserving the installed filter's whole-variant quota and tie order. */
final class VariantFilter {
    private static final long MAX_BYTES = 64L * 1024 * 1024;
    private final List<CachedStatistics> cache = new ArrayList<CachedStatistics>();

    XLog apply(XLog source, int threshold, String experiment) {
        Statistics statistics = statistics(source, experiment);
        boolean[] selected = new boolean[statistics.frequencies.length];
        double quota = source.size() * (threshold / 100d);
        int count = 0;
        for (int variant : statistics.order) {
            ExecutionChecks.check();
            int frequency = statistics.frequencies[variant];
            if (count + frequency > quota) break;
            selected[variant] = true;
            count += frequency;
        }
        XLog output = XFactoryRegistry.instance().currentDefault().createLog(source.getAttributes());
        output.getExtensions().addAll(source.getExtensions());
        output.getClassifiers().addAll(source.getClassifiers());
        if (output.getClassifiers().isEmpty()) output.getClassifiers().add(new XEventNameClassifier());
        // Keep global attribute declarations too; the dependency inadvertently dropped them.
        output.getGlobalTraceAttributes().addAll(source.getGlobalTraceAttributes());
        output.getGlobalEventAttributes().addAll(source.getGlobalEventAttributes());
        for (int i = 0; i < source.size(); i++) {
            ExecutionChecks.check();
            if (selected[statistics.traceVariants[i]]) output.add(source.get(i));
        }
        return output;
    }

    void evictExperiment(String experiment) {
        synchronized (cache) { cache.removeIf(entry -> java.util.Objects.equals(entry.experiment, experiment)); }
    }

    private Statistics statistics(XLog source, String experiment) {
        synchronized (cache) {
            for (Iterator<CachedStatistics> it = cache.iterator(); it.hasNext();) {
                CachedStatistics entry = it.next();
                XLog cachedSource = entry.source.get();
                if (cachedSource == null) { it.remove(); continue; }
                if (cachedSource == source && entry.statistics.traceVariants.length == source.size()
                        && java.util.Objects.equals(entry.experiment, experiment)) return entry.statistics;
            }
        }
        Statistics result = build(source);
        long bytes = result.bytes();
        if (bytes <= MAX_BYTES) synchronized (cache) {
            long used = 0;
            for (CachedStatistics entry : cache) used += entry.statistics.bytes();
            while (!cache.isEmpty() && (used + bytes > MAX_BYTES || cache.size() >= 16)) {
                used -= cache.remove(0).statistics.bytes();
            }
            cache.add(new CachedStatistics(source, experiment, result));
        }
        return result;
    }

    private static Statistics build(XLog log) {
        Map<String, Integer> activities = new HashMap<String, Integer>();
        Map<Sequence, Integer> variants = new HashMap<Sequence, Integer>();
        int[] traceVariants = new int[log.size()];
        int[] frequencies = new int[log.size()];
        int position = 0;
        for (XTrace trace : log) {
            ExecutionChecks.check();
            int[] sequence = new int[trace.size()];
            int eventIndex = 0;
            for (XEvent event : trace) {
                ExecutionChecks.check();
                XAttribute attribute = event.getAttributes().get("concept:name");
                if (attribute == null) throw new IllegalArgumentException("variant_filter requires concept:name on every event");
                String name = attribute.toString();
                Integer activity = activities.get(name);
                if (activity == null) { activity = activities.size(); activities.put(name, activity); }
                sequence[eventIndex++] = activity;
            }
            Sequence key = new Sequence(sequence);
            Integer variant = variants.get(key);
            if (variant == null) { variant = variants.size(); variants.put(key, variant); }
            traceVariants[position++] = variant;
            frequencies[variant]++;
        }
        final int[] counts = Arrays.copyOf(frequencies, variants.size());
        Integer[] ordered = new Integer[counts.length];
        for (int i = 0; i < ordered.length; i++) ordered[i] = i;
        Arrays.sort(ordered, (a, b) -> {
            ExecutionChecks.check();
            int frequency = Integer.compare(counts[b], counts[a]);
            return frequency == 0 ? Integer.compare(b, a) : frequency;
        });
        int[] order = new int[ordered.length];
        for (int i = 0; i < order.length; i++) order[i] = ordered[i];
        return new Statistics(traceVariants, counts, order);
    }

    private static final class Sequence {
        final int[] values;
        final int hash;
        Sequence(int[] values) { this.values = values; this.hash = Arrays.hashCode(values); }
        @Override public int hashCode() { return hash; }
        @Override public boolean equals(Object other) {
            return other instanceof Sequence && Arrays.equals(values, ((Sequence) other).values);
        }
    }
    private static final class Statistics {
        final int[] traceVariants, frequencies, order;
        Statistics(int[] traceVariants, int[] frequencies, int[] order) {
            this.traceVariants = traceVariants; this.frequencies = frequencies; this.order = order;
        }
        long bytes() { return 128L + 4L * (traceVariants.length + 2L * frequencies.length); }
    }
    private static final class CachedStatistics {
        final WeakReference<XLog> source;
        final String experiment;
        final Statistics statistics;
        CachedStatistics(XLog source, String experiment, Statistics statistics) {
            this.source = new WeakReference<XLog>(source); this.experiment = experiment; this.statistics = statistics;
        }
    }
}
