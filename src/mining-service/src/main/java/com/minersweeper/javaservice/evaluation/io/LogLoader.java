package com.minersweeper.javaservice.evaluation.io;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;

public class LogLoader {
    private static final String LOG_CACHE_SIZE_ENV = "PROM_LOG_CACHE_MAX_EXPERIMENTS";
    private static final int DEFAULT_LOG_CACHE_SIZE = 1;

    private final Path logsRoot;
    private final int maxCachedExperiments;
    private final Map<String, CachedLog> logsByExperiment = new LinkedHashMap<String, CachedLog>(16, 0.75f, true);
    private final Map<String, LoadingLog> loadingByExperiment = new LinkedHashMap<String, LoadingLog>();

    public LogLoader(Path logsRoot) {
        this.logsRoot = logsRoot == null ? Paths.get(".") : logsRoot;
        this.maxCachedExperiments = parsePositiveIntEnv(LOG_CACHE_SIZE_ENV, DEFAULT_LOG_CACHE_SIZE);
    }

    public Path resolveLogPath(String rawPath) {
        Path provided = Paths.get(rawPath == null ? "" : rawPath).normalize();
        if (provided.isAbsolute()) {
            return provided;
        }
        return logsRoot.resolve(provided).normalize();
    }

    public XLog loadLog(File file) throws Exception {
        if (!file.exists()) {
            throw new IllegalArgumentException("log not found: " + file.getAbsolutePath());
        }

        XesXmlParser parser = new XesXmlParser();
        List<XLog> logs = parser.parse(file);
        if (logs == null || logs.isEmpty()) {
            throw new IllegalStateException("XES parser returned empty log list");
        }
        return logs.get(0);
    }

    public LogAccess loadForExperiment(String experimentId, String rawPath) throws Exception {
        Path resolvedPath = resolveLogPath(rawPath).toAbsolutePath().normalize();
        String key = normalizeExperimentId(experimentId);
        LoadingLog loading = null;
        boolean shouldRun = false;

        synchronized (this) {
            CachedLog cached = logsByExperiment.get(key);
            if (cached != null && cached.path.equals(resolvedPath)) {
                return LogAccess.hit(cached.log, resolvedPath);
            }
            loading = loadingByExperiment.get(key);
            if (loading == null || !loading.path.equals(resolvedPath)) {
                loading = new LoadingLog(
                    resolvedPath,
                    new FutureTask<XLog>(() -> loadLog(resolvedPath.toFile()))
                );
                loadingByExperiment.put(key, loading);
                shouldRun = true;
            }
        }

        if (shouldRun) {
            loading.task.run();
        }

        XLog loaded;
        try {
            loaded = loading.task.get();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw error;
        } catch (ExecutionException error) {
            Throwable cause = error.getCause();
            if (cause instanceof Exception) {
                throw (Exception) cause;
            }
            throw new RuntimeException(cause);
        }

        synchronized (this) {
            try {
                CachedLog cached = logsByExperiment.get(key);
                if (cached != null && cached.path.equals(resolvedPath)) {
                    return LogAccess.hit(cached.log, resolvedPath);
                }
                if (loadingByExperiment.get(key) == loading && loading.path.equals(resolvedPath)) {
                    logsByExperiment.put(key, new CachedLog(resolvedPath, loaded));
                    trimToMaxSize();
                    return shouldRun ? LogAccess.miss(loaded, resolvedPath) : LogAccess.hit(loaded, resolvedPath);
                }
                CachedLog refreshed = logsByExperiment.get(key);
                if (refreshed != null && refreshed.path.equals(resolvedPath)) {
                    return LogAccess.hit(refreshed.log, resolvedPath);
                }
                logsByExperiment.put(key, new CachedLog(resolvedPath, loaded));
                trimToMaxSize();
                return shouldRun ? LogAccess.miss(loaded, resolvedPath) : LogAccess.hit(loaded, resolvedPath);
            } finally {
                if (loadingByExperiment.get(key) == loading) {
                    loadingByExperiment.remove(key);
                }
            }
        }
    }

    public synchronized void evictExperiment(String experimentId) {
        String normalized = normalizeExperimentId(experimentId);
        logsByExperiment.remove(normalized);
        loadingByExperiment.remove(normalized);
    }

    private void trimToMaxSize() {
        while (logsByExperiment.size() > maxCachedExperiments) {
            Iterator<Map.Entry<String, CachedLog>> iterator = logsByExperiment.entrySet().iterator();
            if (!iterator.hasNext()) {
                break;
            }
            iterator.next();
            iterator.remove();
        }
    }

    private static String normalizeExperimentId(String experimentId) {
        String normalized = experimentId == null ? "" : experimentId.trim();
        return normalized.isEmpty() ? "__default__" : normalized;
    }

    private static int parsePositiveIntEnv(String key, int fallback) {
        String raw = System.getenv(key);
        if (raw == null || raw.trim().isEmpty()) {
            return fallback;
        }
        try {
            int parsed = Integer.parseInt(raw.trim());
            return parsed > 0 ? parsed : fallback;
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static final class CachedLog {
        private final Path path;
        private final XLog log;

        private CachedLog(Path path, XLog log) {
            this.path = path;
            this.log = log;
        }
    }

    private static final class LoadingLog {
        private final Path path;
        private final FutureTask<XLog> task;

        private LoadingLog(Path path, FutureTask<XLog> task) {
            this.path = path;
            this.task = task;
        }
    }

    public static final class LogAccess {
        private final XLog log;
        private final Path path;
        private final boolean cacheHit;

        private LogAccess(XLog log, Path path, boolean cacheHit) {
            this.log = log;
            this.path = path;
            this.cacheHit = cacheHit;
        }

        public XLog log() {
            return log;
        }

        public Path path() {
            return path;
        }

        public boolean cacheHit() {
            return cacheHit;
        }

        private static LogAccess hit(XLog log, Path path) {
            return new LogAccess(log, path, true);
        }

        private static LogAccess miss(XLog log, Path path) {
            return new LogAccess(log, path, false);
        }
    }
}
