package com.minersweeper.javaservice.evaluation.isolation;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.lang.management.ManagementFactory;

/** All budgets belong to the mining service, not to callers or campaign clients. */
public final class WorkerPoolConfig {
    public final int workers;
    public final String heap;
    public final long evaluationMs, graceMs, startupMs, queueMs, killMs;
    public final String workerMain;

    public WorkerPoolConfig(int workers, String heap, long evaluationMs, long graceMs,
                            long startupMs, long queueMs, long killMs, String workerMain) {
        if (workers < 1 || workers > 32 || evaluationMs <= 0 || graceMs < 0 || startupMs <= 0 || queueMs <= 0 || killMs <= 0)
            throw new IllegalArgumentException("Invalid process pool limits");
        parseMemory(heap);
        this.workers = workers; this.heap = heap; this.evaluationMs = evaluationMs;
        this.graceMs = graceMs; this.startupMs = startupMs; this.queueMs = queueMs;
        this.killMs = killMs; this.workerMain = workerMain;
    }

    public static WorkerPoolConfig fromEnvironment() {
        WorkerPoolConfig config = new WorkerPoolConfig(integer("PROM_WORKER_COUNT", 1), env("PROM_WORKER_XMX", "8g"),
            seconds("PROM_EVALUATION_TIMEOUT_SECONDS", 300), seconds("PROM_CANCEL_GRACE_SECONDS", 10),
            seconds("PROM_WORKER_STARTUP_SECONDS", 120), seconds("PROM_WORKER_QUEUE_SECONDS", 30),
            seconds("PROM_WORKER_KILL_SECONDS", 10), IsolatedWorkerMain.class.getName());
        long limit = memoryLimit();
        long budget = config.workers * (parseMemory(config.heap) + parseMemory(env("PROM_WORKER_NATIVE_RESERVE", "1g")))
            + Runtime.getRuntime().maxMemory();
        if (limit > 0 && budget > limit)
            throw new IllegalArgumentException("Worker heaps + native reserves + coordinator heap exceed physical/container memory limit; reduce PROM_WORKER_COUNT or PROM_WORKER_XMX");
        return config;
    }

    public long httpTimeoutSeconds() {
        // Covers queued admission, cold start, a task, forced shutdown and replacement.
        return (queueMs + 3 * startupMs + evaluationMs + graceMs + killMs + 999) / 1000 + 15;
    }

    public static long parseMemory(String value) {
        String text = value.trim().toLowerCase(java.util.Locale.ROOT);
        long multiplier = 1;
        if (text.endsWith("g")) { multiplier = 1024L*1024*1024; text = text.substring(0,text.length()-1); }
        else if (text.endsWith("m")) { multiplier = 1024L*1024; text = text.substring(0,text.length()-1); }
        else if (text.endsWith("k")) { multiplier = 1024L; text = text.substring(0,text.length()-1); }
        long result = Math.multiplyExact(Long.parseLong(text), multiplier);
        if (result < 16L*1024*1024) throw new IllegalArgumentException("Worker heap/reserve must be at least 16 MiB");
        return result;
    }

    private static long memoryLimit() {
        long limit = ((com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean()).getTotalPhysicalMemorySize();
        for (String path : new String[]{"/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"}) {
            try {
                String text = new String(Files.readAllBytes(Paths.get(path)), java.nio.charset.StandardCharsets.UTF_8).trim();
                if (!"max".equals(text)) { long value = Long.parseLong(text); if (value > 0) limit = Math.min(limit, value); }
            } catch (Exception ignored) { /* May run outside a memory cgroup. */ }
        }
        return limit;
    }
    private static int integer(String name, int fallback) { return Integer.parseInt(env(name, Integer.toString(fallback))); }
    private static long seconds(String name, int fallback) { return Math.multiplyExact(Long.parseLong(env(name, Integer.toString(fallback))), 1000L); }
    private static String env(String name, String fallback) { String v = System.getenv(name); return v == null || v.trim().isEmpty() ? fallback : v.trim(); }
}
