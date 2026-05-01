import com.minersweeper.javaservice.evaluation.io.LogLoader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.junit.Test;

import static org.junit.Assert.assertFalse;
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
