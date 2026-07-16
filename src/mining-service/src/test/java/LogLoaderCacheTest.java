import com.minersweeper.javaservice.evaluation.io.LogLoader;
import java.io.IOException;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;
import org.junit.Test;
import org.deckfour.xes.model.XLog;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotSame;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

public class LogLoaderCacheTest {

    @Test
    public void sameExperimentAndPathHitsCacheOnSecondCall() throws Exception {
        Path tempDir = Files.createTempDirectory("log-loader-cache-test");
        try {
            Path log = TestFixtures.createTinyLog(tempDir, "sample.xes");
            LogLoader loader = new LogLoader(tempDir);

            LogLoader.LogAccess first = loader.loadForExperiment("run_1", log.getFileName().toString());
            LogLoader.LogAccess second = loader.loadForExperiment("run_1", log.getFileName().toString());

            assertFalse(first.cacheHit());
            assertTrue(second.cacheHit());
            assertSame(first.log(), second.log());
        } finally {
            deleteRecursively(tempDir);
        }
    }

    @Test
    public void sameExperimentWithDifferentPathReloadsLog() throws Exception {
        Path tempDir = Files.createTempDirectory("log-loader-path-change-test");
        try {
            Path logA = TestFixtures.createTinyLog(tempDir, "a.xes");
            Path logB = TestFixtures.createTinyLog(tempDir, "b.xes");
            LogLoader loader = new LogLoader(tempDir);

            LogLoader.LogAccess first = loader.loadForExperiment("run_1", logA.getFileName().toString());
            LogLoader.LogAccess second = loader.loadForExperiment("run_1", logB.getFileName().toString());

            assertFalse(first.cacheHit());
            assertFalse(second.cacheHit());
            assertNotSame(first.log(), second.log());
        } finally {
            deleteRecursively(tempDir);
        }
    }

    @Test
    public void evictExperimentForcesReload() throws Exception {
        Path tempDir = Files.createTempDirectory("log-loader-evict-test");
        try {
            Path log = TestFixtures.createTinyLog(tempDir, "sample.xes");
            LogLoader loader = new LogLoader(tempDir);

            LogLoader.LogAccess first = loader.loadForExperiment("run_1", log.getFileName().toString());
            LogLoader.LogAccess second = loader.loadForExperiment("run_1", log.getFileName().toString());
            loader.evictExperiment("run_1");
            LogLoader.LogAccess third = loader.loadForExperiment("run_1", log.getFileName().toString());

            assertFalse(first.cacheHit());
            assertTrue(second.cacheHit());
            assertFalse(third.cacheHit());
            assertNotSame(second.log(), third.log());
        } finally {
            deleteRecursively(tempDir);
        }
    }

    @Test
    public void secondExperimentEvictsFirstWhenCacheSizeIsOne() throws Exception {
        Path tempDir = Files.createTempDirectory("log-loader-size-one-test");
        try {
            Path log = TestFixtures.createTinyLog(tempDir, "sample.xes");
            LogLoader loader = new LogLoader(tempDir);

            LogLoader.LogAccess firstRunFirstLoad = loader.loadForExperiment("run_1", log.getFileName().toString());
            LogLoader.LogAccess secondRunLoad = loader.loadForExperiment("run_2", log.getFileName().toString());
            LogLoader.LogAccess firstRunReload = loader.loadForExperiment("run_1", log.getFileName().toString());

            assertFalse(firstRunFirstLoad.cacheHit());
            assertFalse(secondRunLoad.cacheHit());
            assertFalse(firstRunReload.cacheHit());
            assertNotSame(firstRunFirstLoad.log(), firstRunReload.log());
        } finally {
            deleteRecursively(tempDir);
        }
    }

    @Test
    public void concurrentLoadsForSameExperimentShareSingleParse() throws Exception {
        Path tempDir = Files.createTempDirectory("log-loader-concurrent-test");
        try {
            Path log = TestFixtures.createTinyLog(tempDir, "sample.xes");
            final CountDownLatch enteredLoad = new CountDownLatch(1);
            final CountDownLatch releaseLoad = new CountDownLatch(1);
            final AtomicInteger loadCalls = new AtomicInteger(0);

            LogLoader loader = new LogLoader(tempDir) {
                @Override
                public XLog loadLog(File file) throws Exception {
                    loadCalls.incrementAndGet();
                    enteredLoad.countDown();
                    releaseLoad.await();
                    return super.loadLog(file);
                }
            };

            final LogLoader.LogAccess[] results = new LogLoader.LogAccess[2];
            final Throwable[] failures = new Throwable[2];

            Thread first = new Thread(() -> runLoad(loader, log, results, failures, 0));
            Thread second = new Thread(() -> runLoad(loader, log, results, failures, 1));

            first.start();
            enteredLoad.await();
            second.start();
            releaseLoad.countDown();
            first.join();
            second.join();

            assertEquals(1, loadCalls.get());
            assertSame(results[0].log(), results[1].log());
            assertFalse(results[0].cacheHit() && results[1].cacheHit());
            assertTrue(results[0].cacheHit() || results[1].cacheHit());
            assertNoFailure(failures[0]);
            assertNoFailure(failures[1]);
        } finally {
            deleteRecursively(tempDir);
        }
    }

    private static void runLoad(
        LogLoader loader,
        Path log,
        LogLoader.LogAccess[] results,
        Throwable[] failures,
        int index
    ) {
        try {
            results[index] = loader.loadForExperiment("run_1", log.getFileName().toString());
        } catch (Throwable error) {
            failures[index] = error;
        }
    }

    private static void assertNoFailure(Throwable failure) throws Exception {
        if (failure == null) {
            return;
        }
        if (failure instanceof Exception) {
            throw (Exception) failure;
        }
        throw new RuntimeException(failure);
    }

    private static void deleteRecursively(Path path) throws IOException {
        if (path == null || !Files.exists(path)) {
            return;
        }
        try (Stream<Path> stream = Files.walk(path)) {
            stream.sorted((a, b) -> b.compareTo(a))
                .forEach(p -> {
                    try {
                        Files.deleteIfExists(p);
                    } catch (IOException ignored) {
                    }
                });
        }
    }
}
