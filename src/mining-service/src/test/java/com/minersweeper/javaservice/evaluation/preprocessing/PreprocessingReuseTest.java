package com.minersweeper.javaservice.evaluation.preprocessing;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.factory.XFactory;
import org.deckfour.xes.factory.XFactoryRegistry;
import org.deckfour.xes.model.*;
import org.deckfour.xes.info.impl.XLogInfoImpl;
import org.processmining.logfiltering.parameters.MatrixFilterParameter;
import org.processmining.logfiltering.plugins.VariantCounterPlugin;
import org.junit.Assert;
import org.junit.Test;

public class PreprocessingReuseTest {
    private static XLog log(String[]... sequences) {
        XFactory factory = XFactoryRegistry.instance().currentDefault();
        XLog log = factory.createLog();
        log.getClassifiers().add(new XEventNameClassifier());
        for (int i = 0; i < sequences.length; i++) {
            XTrace trace = factory.createTrace();
            trace.getAttributes().put("concept:name", factory.createAttributeLiteral("concept:name", "case" + i, null));
            for (String activity : sequences[i]) {
                XEvent event = factory.createEvent();
                event.getAttributes().put("concept:name", factory.createAttributeLiteral("concept:name", activity, null));
                trace.add(event);
            }
            log.add(trace);
        }
        return log;
    }
    private static PipelineRequest request(String key, String parameter, Object value) {
        PipelineRequest request = new PipelineRequest();
        request.experiment_id = "test";
        request.pipeline = new PipelineRequest.PipelineConfig();
        request.pipeline.preprocessing = new PipelineRequest.PreprocessingConfig();
        request.pipeline.preprocessing.key = key;
        request.pipeline.preprocessing.parameters = new HashMap<String, Object>();
        request.pipeline.preprocessing.parameters.put(parameter, value);
        return request;
    }
    private static List<String> cases(XLog log) {
        List<String> result = new ArrayList<String>();
        for (XTrace trace : log) result.add(trace.getAttributes().get("concept:name").toString());
        return result;
    }
    private static XLog tiny() { return log(new String[]{"A"}, new String[]{"B"}); }
    private static void awaitWaiting(Thread thread) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
        while (thread.getState() != Thread.State.TIMED_WAITING && System.nanoTime() < deadline) Thread.yield();
        Assert.assertEquals("waiter must be attached before producer is released", Thread.State.TIMED_WAITING, thread.getState());
    }

    @Test public void variantMatchesDependencyAcrossFrequenciesTiesAndThresholds() {
        Random random = new Random(20260930);
        VariantFilter filter = new VariantFilter();
        for (int run = 0; run < 15; run++) {
            String[][] sequences = new String[60][];
            for (int i = 0; i < sequences.length; i++) {
                sequences[i] = new String[1 + random.nextInt(5)];
                for (int j = 0; j < sequences[i].length; j++) sequences[i][j] = "activity" + random.nextInt(4) + "|";
            }
            XLog source = log(sequences);
            for (int threshold : new int[]{0, 1, 25, 29, 50, 80, 99, 100}) {
                XLog expected = VariantCounterPlugin.run(null, source, new MatrixFilterParameter(threshold, XLogInfoImpl.NAME_CLASSIFIER));
                Assert.assertEquals(cases(expected), cases(filter.apply(source, threshold, "parity")));
            }
        }
    }
    @Test public void tiesSelectLaterVariantAndPreserveSourceOrder() {
        XLog source = log(new String[]{"A"}, new String[]{"B"}, new String[]{"A"}, new String[]{"B"});
        Assert.assertEquals(Arrays.asList("case1", "case3"), cases(new VariantFilter().apply(source, 50, "test")));
    }
    @Test public void quotaStopsInsteadOfSkippingAnOversizedVariant() {
        XLog source = log(new String[]{"A"}, new String[]{"A"}, new String[]{"A"}, new String[]{"B"});
        Assert.assertTrue(new VariantFilter().apply(source, 50, "test").isEmpty());
    }
    @Test public void ambiguousConcatenationsAreDistinctVariants() {
        XLog source = log(new String[]{"AB", "C"}, new String[]{"A", "BC"});
        Assert.assertEquals(Collections.singletonList("case1"), cases(new VariantFilter().apply(source, 50, "test")));
    }
    @Test public void cacheReusesFiltersAcrossMinersAndCanonicalParameters() throws Exception {
        XLog source = tiny();
        PreprocessingPipeline pipeline = new PreprocessingPipeline(1024 * 1024);
        PipelineRequest first = request("variant_filter", "keep_threshold_vf", 100);
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, first).cacheStatus());
        PipelineRequest second = request("VARIANT_FILTER", "keep_threshold_vf", "999");
        second.pipeline.miner = new PipelineRequest.MinerConfig();
        second.pipeline.miner.key = "alpha";
        second.metrics = Collections.singletonList("fitness");
        second.pipeline.preprocessing.method = "display metadata";
        second.pipeline.preprocessing.parameters.put("unused", 33);
        second.pipeline.preprocessings = Collections.singletonList(second.pipeline.preprocessing);
        Assert.assertEquals("hit", pipeline.applyWithCache(null, source, second).cacheStatus());
        second.pipeline.preprocessing.parameters.put("keep_threshold_vf", 50);
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, second).cacheStatus());
    }
    @Test public void sourceIdentityExperimentAndCleanupSeparateEntries() throws Exception {
        XLog source = tiny();
        PreprocessingPipeline pipeline = new PreprocessingPipeline(1024 * 1024);
        PipelineRequest request = request("variant_filter", "keep_threshold_vf", 100);
        request.experiment_id = " test ";
        pipeline.apply(null, source, request);
        request.experiment_id = "test";
        Assert.assertEquals("hit", pipeline.applyWithCache(null, source, request).cacheStatus());
        Assert.assertEquals("miss", pipeline.applyWithCache(null, (XLog) source.clone(), request).cacheStatus());
        request.experiment_id = "other";
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, request).cacheStatus());
        request.experiment_id = "test";
        pipeline.evictExperiment("test");
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, request).cacheStatus());
    }
    @Test public void orderedFilterChainsHaveDifferentKeys() throws Exception {
        XLog source = tiny();
        PreprocessingPipeline pipeline = new PreprocessingPipeline(1024 * 1024);
        PipelineRequest request = request("variant_filter", "keep_threshold_vf", 100);
        PipelineRequest.PreprocessingConfig variant = request.pipeline.preprocessing;
        PipelineRequest.PreprocessingConfig projection = request("projection_filter", "keep_threshold_p", 100).pipeline.preprocessing;
        request.pipeline.preprocessings = Arrays.asList(variant, projection);
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, request).cacheStatus());
        request.pipeline.preprocessings = Arrays.asList(projection, variant);
        Assert.assertEquals("miss", pipeline.applyWithCache(null, source, request).cacheStatus());
        Assert.assertEquals("hit", pipeline.applyWithCache(null, source, request).cacheStatus());
    }
    @Test public void cachedCopiesIsolateEventsNestedAttributesAndGlobalDeclarations() throws Exception {
        XLog source = tiny();
        XFactory factory = XFactoryRegistry.instance().currentDefault();
        XAttribute name = source.get(0).get(0).getAttributes().get("concept:name");
        name.getAttributes().put("nested", factory.createAttributeLiteral("nested", "original", null));
        source.getGlobalEventAttributes().add(factory.createAttributeLiteral("global", "original", null));
        source.getClassifiers().clear();
        PreprocessingPipeline pipeline = new PreprocessingPipeline(1024 * 1024);
        PipelineRequest request = request("variant_filter", "keep_threshold_vf", 100);
        XLog first = pipeline.apply(null, source, request);
        ((XAttributeLiteral) first.get(0).get(0).getAttributes().get("concept:name")).setValue("mutated");
        ((XAttributeLiteral) first.get(0).get(0).getAttributes().get("concept:name").getAttributes().get("nested")).setValue("mutated");
        ((XAttributeLiteral) first.getGlobalEventAttributes().get(0)).setValue("mutated");
        first.getClassifiers().get(0).setName("mutated classifier");
        first.getClassifiers().clear();
        XLog second = pipeline.apply(null, source, request);
        Assert.assertEquals("A", second.get(0).get(0).getAttributes().get("concept:name").toString());
        Assert.assertEquals("original", second.get(0).get(0).getAttributes().get("concept:name").getAttributes().get("nested").toString());
        Assert.assertEquals("original", second.getGlobalEventAttributes().get(0).toString());
        Assert.assertEquals(1, second.getClassifiers().size());
        Assert.assertEquals(new XEventNameClassifier().name(), second.getClassifiers().get(0).name());
        Assert.assertEquals("A", name.toString());
        Assert.assertTrue(source.getClassifiers().isEmpty());
    }
    @Test public void failuresAreNotCached() throws Exception {
        PreprocessedLogCache cache = new PreprocessedLogCache(1024 * 1024);
        XLog source = tiny();
        try { cache.get(source, "test", "filter", () -> { throw new IllegalArgumentException("failed"); }); Assert.fail(); }
        catch (IllegalArgumentException expected) { Assert.assertEquals("failed", expected.getMessage()); }
        Assert.assertEquals("miss", cache.get(source, "test", "filter", () -> source).cacheStatus());
    }
    @Test public void budgetEvictsAndOversizedOutputsArePrivate() throws Exception {
        XLog source = tiny();
        long bytes = PreprocessedLogCache.estimateBytes(source, Long.MAX_VALUE);
        PreprocessedLogCache cache = new PreprocessedLogCache(bytes);
        Assert.assertEquals("miss", cache.get(source, "test", "a", () -> (XLog) source.clone()).cacheStatus());
        Assert.assertEquals("miss", cache.get(source, "test", "b", () -> (XLog) source.clone()).cacheStatus());
        Assert.assertTrue(cache.retainedBytes() <= bytes);
        Assert.assertEquals(1, cache.size());
        Assert.assertEquals("miss", cache.get(source, "test", "a", () -> (XLog) source.clone()).cacheStatus());
        PreprocessedLogCache small = new PreprocessedLogCache(1);
        PreprocessingPipeline.Access bypass = small.get(source, "test", "a", () -> (XLog) source.clone());
        Assert.assertEquals("bypass_size", bypass.cacheStatus());
        Assert.assertNotSame(source.get(0).get(0), bypass.log().get(0).get(0));
        Assert.assertEquals(0, small.size());
        cache.evictExperiment("test");
        Assert.assertEquals(0, cache.retainedBytes());
    }
    @Test public void compactSelectionsFitWithoutRetainingEventPayload() throws Exception {
        XLog source = tiny();
        PreprocessedLogCache cache = new PreprocessedLogCache(2048);
        PreprocessingPipeline.Access first = cache.get(source, "test", "filter", () -> source);
        Assert.assertEquals("miss", first.cacheStatus());
        Assert.assertTrue(PreprocessedLogCache.estimateBytes(source, Long.MAX_VALUE) > 2048);
        Assert.assertTrue(cache.retainedBytes() < 2048);
        Assert.assertNotSame(source.get(0).get(0), first.log().get(0).get(0));
        Assert.assertEquals("hit", cache.get(source, "test", "filter", () -> { throw new AssertionError("not reused"); }).cacheStatus());
    }

    @Test public void identicalConcurrentCallsComputeOnceAndReturnPrivateCopies() throws Exception {
        PreprocessedLogCache cache = new PreprocessedLogCache(1024 * 1024);
        XLog source = tiny();
        AtomicInteger calls = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<PreprocessingPipeline.Access>> results = new ArrayList<Future<PreprocessingPipeline.Access>>();
            PreprocessedLogCache.Loader loader = () -> { calls.incrementAndGet(); started.countDown(); release.await(); return source; };
            for (int i = 0; i < 4; i++) results.add(pool.submit(() -> cache.get(source, "test", "filter", loader)));
            Assert.assertTrue(started.await(2, TimeUnit.SECONDS));
            release.countDown();
            Set<XLog> identities = Collections.newSetFromMap(new IdentityHashMap<XLog, Boolean>());
            for (Future<PreprocessingPipeline.Access> result : results) identities.add(result.get(5, TimeUnit.SECONDS).log());
            Assert.assertEquals(1, calls.get());
            Assert.assertEquals(4, identities.size());
        } finally { release.countDown(); pool.shutdownNow(); }
    }
    @Test public void cancellingWaiterLeavesProducerAndCacheAlive() throws Exception {
        PreprocessedLogCache cache = new PreprocessedLogCache(1024 * 1024);
        XLog source = tiny();
        CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1), waiterStarted = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<PreprocessingPipeline.Access> producer = pool.submit(() -> cache.get(source, "test", "filter", () -> { started.countDown(); release.await(); return source; }));
            Assert.assertTrue(started.await(2, TimeUnit.SECONDS));
            Future<PreprocessingPipeline.Access> waiter = pool.submit(() -> { waiterStarted.countDown(); return cache.get(source, "test", "filter", () -> { throw new AssertionError("duplicate work"); }); });
            Assert.assertTrue(waiterStarted.await(2, TimeUnit.SECONDS));
            waiter.cancel(true);
            release.countDown();
            Assert.assertEquals("miss", producer.get(5, TimeUnit.SECONDS).cacheStatus());
            Assert.assertEquals("hit", cache.get(source, "test", "filter", () -> { throw new AssertionError("cache lost"); }).cacheStatus());
        } finally { release.countDown(); pool.shutdownNow(); }
    }
    @Test public void cancelledProducerDoesNotCancelAnotherRequest() throws Exception {
        PreprocessedLogCache cache = new PreprocessedLogCache(1024 * 1024);
        XLog source = tiny();
        AtomicInteger calls = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            PreprocessedLogCache.Loader loader = () -> {
                if (calls.incrementAndGet() == 1) { started.countDown(); release.await(); throw new CancellationException("producer cancelled"); }
                return source;
            };
            Future<PreprocessingPipeline.Access> producer = pool.submit(() -> cache.get(source, "test", "filter", loader));
            Assert.assertTrue(started.await(2, TimeUnit.SECONDS));
            CountDownLatch waiterStarted = new CountDownLatch(1);
            Thread[] waiterThread = new Thread[1];
            Future<PreprocessingPipeline.Access> waiter = pool.submit(() -> {
                waiterThread[0] = Thread.currentThread(); waiterStarted.countDown();
                return cache.get(source, "test", "filter", loader);
            });
            Assert.assertTrue(waiterStarted.await(2, TimeUnit.SECONDS));
            awaitWaiting(waiterThread[0]);
            release.countDown();
            try { producer.get(5, TimeUnit.SECONDS); Assert.fail(); }
            catch (ExecutionException expected) { Assert.assertTrue(expected.getCause() instanceof CancellationException); }
            Assert.assertEquals(2, waiter.get(5, TimeUnit.SECONDS).log().size());
            Assert.assertEquals(2, calls.get());
        } finally { release.countDown(); pool.shutdownNow(); }
    }
    @Test public void disabledCacheAndNoFiltersPreserveUncachedPath() throws Exception {
        XLog source = tiny();
        PreprocessingPipeline pipeline = new PreprocessingPipeline(0);
        PipelineRequest request = request("variant_filter", "keep_threshold_vf", 100);
        Assert.assertEquals("disabled", pipeline.applyWithCache(null, source, request).cacheStatus());
        request.pipeline.preprocessing = null;
        Assert.assertEquals("none", pipeline.applyWithCache(null, source, request).cacheStatus());
        Assert.assertSame(source, pipeline.apply(null, source, request));
    }
}
