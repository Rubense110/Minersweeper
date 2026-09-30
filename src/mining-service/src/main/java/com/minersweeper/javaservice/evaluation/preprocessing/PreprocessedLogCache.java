package com.minersweeper.javaservice.evaluation.preprocessing;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.lang.ref.WeakReference;
import java.io.*;
import java.util.IdentityHashMap;
import org.deckfour.xes.classification.XEventClassifier;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.deckfour.xes.factory.XFactory;
import org.deckfour.xes.factory.XFactoryRegistry;
import org.deckfour.xes.model.*;

/** Bounded snapshots for immutable source logs. Each cached consumer gets its own deep copy. */
final class PreprocessedLogCache {
    interface Loader { XLog load() throws Exception; }
    private final long maxBytes;
    private final List<Entry> entries = new ArrayList<Entry>();
    private long usedBytes;

    PreprocessedLogCache(long maxBytes) { this.maxBytes = Math.max(0L, maxBytes); }

    PreprocessingPipeline.Access get(XLog source, String experiment, String parameters, Loader loader) throws Exception {
        if (maxBytes == 0L) return new PreprocessingPipeline.Access(loader.load(), "disabled");
        for (;;) {
            ExecutionChecks.check();
            Entry entry = null;
            boolean owner = false;
            synchronized (entries) {
                purge();
                for (Entry candidate : entries) {
                    if (candidate.source.get() == source && candidate.traceCount == source.size()
                            && Objects.equals(candidate.experiment, experiment) && candidate.parameters.equals(parameters)) {
                        entry = candidate; break;
                    }
                }
                if (entry != null) { entries.remove(entry); entries.add(entry); }
                else {
                    // A bounded number of pending entries also prevents unbounded metadata growth.
                    trim(0L, 31);
                    if (entries.size() < 32) {
                        entry = new Entry(source, experiment, parameters);
                        entries.add(entry);
                        owner = true;
                    }
                }
            }
            if (entry == null) return new PreprocessingPipeline.Access(loader.load(), "bypass_capacity");
            if (owner) {
                try {
                    XLog output = loader.load();
                    Snapshot snapshot = Snapshot.create(source, output, maxBytes);
                    long bytes = snapshot.bytes;
                    if (bytes > maxBytes) {
                        // Never share the owner's mutable output with waiters when bypassing storage.
                        synchronized (entries) { entries.remove(entry); }
                        entry.future.complete(null);
                        return new PreprocessingPipeline.Access(output, "bypass_size");
                    }
                    synchronized (entries) {
                        trim(bytes, 31);
                        if (entries.contains(entry)) { entry.bytes = bytes; usedBytes += bytes; }
                        entry.future.complete(snapshot);
                    }
                    return new PreprocessingPipeline.Access(snapshot.copy(source), "miss");
                } catch (Throwable failure) {
                    synchronized (entries) { remove(entry); }
                    entry.future.completeExceptionally(failure);
                    if (failure instanceof Error) throw (Error) failure;
                    throw (Exception) failure;
                }
            }
            try {
                Snapshot snapshot;
                for (;;) {
                    ExecutionChecks.check();
                    try { snapshot = entry.future.get(100L, TimeUnit.MILLISECONDS); break; }
                    catch (TimeoutException pending) { /* Check cancellation while another request computes. */ }
                }
                if (snapshot == null) return new PreprocessingPipeline.Access(loader.load(), "bypass_size");
                return new PreprocessingPipeline.Access(snapshot.copy(source), "hit");
            } catch (ExecutionException failure) {
                Throwable cause = failure.getCause();
                // The producer's cancellation belongs to that request. A live waiter may retry.
                if (cause instanceof CancellationException || cause instanceof InterruptedException
                        || cause instanceof ExecutionChecks.DeadlineExceeded) continue;
                if (cause instanceof Error) throw (Error) cause;
                throw (Exception) cause;
            } catch (CancellationException producerCancelled) {
                ExecutionChecks.check();
                continue;
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw interrupted;
            }
        }
    }

    void evictExperiment(String experiment) {
        synchronized (entries) {
            for (Iterator<Entry> it = entries.iterator(); it.hasNext();) {
                Entry entry = it.next();
                if (Objects.equals(entry.experiment, experiment)) { usedBytes -= entry.bytes; it.remove(); }
            }
        }
    }

    long retainedBytes() { synchronized (entries) { purge(); return usedBytes; } }
    int size() { synchronized (entries) { purge(); return entries.size(); } }

    private void purge() {
        for (Iterator<Entry> it = entries.iterator(); it.hasNext();) {
            Entry entry = it.next();
            if (entry.source.get() == null) { usedBytes -= entry.bytes; it.remove(); }
        }
    }
    private void remove(Entry entry) { if (entries.remove(entry)) usedBytes -= entry.bytes; }
    private void trim(long additionalBytes, int maxEntries) {
        for (Iterator<Entry> it = entries.iterator(); it.hasNext()
                && (usedBytes + additionalBytes > maxBytes || entries.size() > maxEntries);) {
            Entry entry = it.next();
            if (entry.future.isDone()) { usedBytes -= entry.bytes; it.remove(); }
        }
    }

    static XLog copy(XLog source) {
        XLog output = copyMetadata(source);
        for (XTrace trace : source) output.add(copyTrace(trace));
        return output;
    }

    private static XTrace copyTrace(XTrace trace) {
        ExecutionChecks.check();
        XTrace copied = XFactoryRegistry.instance().currentDefault().createTrace((XAttributeMap) trace.getAttributes().clone());
        for (XEvent event : trace) {
            ExecutionChecks.check();
            copied.add((XEvent) event.clone());
        }
        return copied;
    }

    private static XLog copyMetadata(XLog source) {
        XFactory factory = XFactoryRegistry.instance().currentDefault();
        XLog output = factory.createLog((XAttributeMap) source.getAttributes().clone());
        output.getExtensions().addAll(source.getExtensions());
        for (XEventClassifier classifier : source.getClassifiers()) output.getClassifiers().add(copyClassifier(classifier));
        for (XAttribute attribute : source.getGlobalTraceAttributes()) output.getGlobalTraceAttributes().add((XAttribute) attribute.clone());
        for (XAttribute attribute : source.getGlobalEventAttributes()) output.getGlobalEventAttributes().add((XAttribute) attribute.clone());
        return output;
    }

    private static XEventClassifier copyClassifier(XEventClassifier classifier) {
        // Classifiers have mutable names and key arrays. Preserve their concrete semantics.
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ObjectOutputStream writer = new ObjectOutputStream(bytes)) { writer.writeObject(classifier); }
            try (ObjectInputStream reader = new ObjectInputStream(new ByteArrayInputStream(bytes.toByteArray()))) {
                return (XEventClassifier) reader.readObject();
            }
        } catch (IOException | ClassNotFoundException failure) {
            throw new IllegalArgumentException("cannot copy log classifier: " + classifier.getClass().getName(), failure);
        }
    }

    private static final class Snapshot {
        final XLog log;
        final int[] sourceTraces;
        final long bytes;
        Snapshot(XLog log, int[] sourceTraces, long bytes) { this.log = log; this.sourceTraces = sourceTraces; this.bytes = bytes; }

        static Snapshot create(XLog source, XLog output, long limit) {
            // Whole original traces can be represented by indices. No event payload or source
            // reference is retained, and different thresholds fit without pinning entire logs.
            IdentityHashMap<XTrace, Integer> positions = new IdentityHashMap<XTrace, Integer>();
            for (int i = 0; i < source.size(); i++) { ExecutionChecks.check(); positions.put(source.get(i), i); }
            int[] selected = new int[output.size()];
            for (int i = 0; i < output.size(); i++) {
                ExecutionChecks.check();
                Integer position = positions.get(output.get(i));
                if (position == null) return new Snapshot(output, null, estimateBytes(output, limit));
                selected[i] = position;
            }
            XLog metadata = copyMetadata(output);
            return new Snapshot(metadata, selected, estimateBytes(metadata, limit) + 64L + 4L * selected.length);
        }

        XLog copy(XLog source) {
            if (sourceTraces == null) return PreprocessedLogCache.copy(log);
            XLog output = copyMetadata(log);
            for (int position : sourceTraces) output.add(copyTrace(source.get(position)));
            return output;
        }
    }

    /** Conservative payload estimate, not an RSS cap; stop as soon as the entry is too large. */
    static long estimateBytes(XLog log, long limit) {
        long bytes = 256L + attributesBytes(log.getAttributes().values(), limit);
        bytes += attributesBytes(log.getGlobalTraceAttributes(), limit);
        bytes += attributesBytes(log.getGlobalEventAttributes(), limit);
        bytes += 16L * log.getExtensions().size();
        for (XEventClassifier classifier : log.getClassifiers()) {
            bytes += 224L + 4L * classifier.name().length();
            for (String key : classifier.getDefiningAttributeKeys()) bytes += 64L + 4L * key.length();
        }
        for (XTrace trace : log) {
            ExecutionChecks.check();
            bytes += 192L + 16L * trace.size() + attributesBytes(trace.getAttributes().values(), limit);
            if (bytes > limit) return bytes;
            for (XEvent event : trace) {
                ExecutionChecks.check();
                bytes += 192L + attributesBytes(event.getAttributes().values(), limit);
                if (bytes > limit) return bytes;
            }
        }
        return bytes;
    }
    private static long attributesBytes(Iterable<XAttribute> attributes, long limit) {
        long bytes = 64L;
        Deque<Iterator<XAttribute>> pending = new ArrayDeque<Iterator<XAttribute>>();
        pending.push(attributes.iterator());
        while (!pending.isEmpty()) {
            ExecutionChecks.check();
            Iterator<XAttribute> current = pending.peek();
            if (!current.hasNext()) { pending.pop(); continue; }
            XAttribute attribute = current.next();
            bytes += 224L + 4L * attribute.getKey().length();
            if (attribute instanceof XAttributeLiteral) bytes += 4L * ((XAttributeLiteral) attribute).getValue().length();
            if (bytes > limit) return bytes;
            if (attribute.hasAttributes()) pending.push(attribute.getAttributes().values().iterator());
            if (attribute instanceof XAttributeCollection) pending.push(((XAttributeCollection) attribute).getCollection().iterator());
        }
        return bytes;
    }

    private static final class Entry {
        final WeakReference<XLog> source;
        final int traceCount;
        final String experiment, parameters;
        final CompletableFuture<Snapshot> future = new CompletableFuture<Snapshot>();
        long bytes;
        Entry(XLog source, String experiment, String parameters) {
            this.source = new WeakReference<XLog>(source); this.traceCount = source.size();
            this.experiment = experiment; this.parameters = parameters;
        }
    }
}
