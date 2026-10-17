package com.minersweeper.javaservice.evaluation.isolation;

import java.io.*;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

/** Owned Linux process session; replacement waits for both leader and descendants. */
final class WorkerProcess {
    final WorkerPoolConfig config;
    final Path root;
    final Path logsRoot;
    final Set<String> pendingCleanup = new java.util.concurrent.ConcurrentSkipListSet<String>();
    Path home;
    volatile Process process;
    volatile long pid;
    volatile String generation;
    volatile boolean recovering;
    private BufferedWriter commands;

    WorkerProcess(WorkerPoolConfig config, Path root, Path logsRoot) {
        this.config = config; this.root = root; this.logsRoot = logsRoot;
    }

    synchronized void start(BooleanSupplier cancelled) throws Exception {
        if (process != null && process.isAlive()) return;
        if (process != null) stop();
        generation = UUID.randomUUID().toString();
        home = Files.createDirectories(root.resolve(generation));
        List<String> command = new ArrayList<String>(Arrays.asList("setsid", "--",
            Paths.get(System.getProperty("java.home"), "bin", "java").toString(),
            "-Xms16m", "-Xmx"+config.heap, "-XX:+UseG1GC", "-XX:ActiveProcessorCount=1",
            "-Djava.library.path="+System.getProperty("java.library.path"),
            "-cp", System.getProperty("java.class.path"), config.workerMain,
            home.toString(), logsRoot.toString()));
        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(true).redirectOutput(home.resolve("worker.log").toFile());
        builder.environment().remove("JAVA_TOOL_OPTIONS");
        builder.environment().remove("_JAVA_OPTIONS");
        builder.environment().remove("JDK_JAVA_OPTIONS");
        builder.environment().put("PROM_MAX_CONCURRENT_EVALUATIONS", "1");
        builder.environment().put("PROM_EVALUATION_ISOLATION_POLICY", "isolated-jvm-pool-v1");
        process = builder.start();
        try {
            pid = processId(process);
            commands = new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));
            long deadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.startupMs);
            while (!Files.exists(home.resolve("ready"))) {
                if (cancelled.getAsBoolean()) throw new com.minersweeper.javaservice.evaluation.ExperimentCancelledException("Cancelled during worker startup");
                if (!process.isAlive()) throw new IOException("Worker exited during startup; see "+home.resolve("worker.log"));
                if (System.nanoTime() >= deadline) throw new IOException("Worker startup timed out; see "+home.resolve("worker.log"));
                Thread.sleep(10);
            }
            System.err.println("worker_ready generation="+generation+" pid="+pid);
        } catch (Exception error) {
            stop(); throw error;
        }
    }

    Path send(WorkerProtocol.Command command) throws Exception {
        String name = UUID.randomUUID().toString()+".request";
        Path file = home.resolve(name);
        WorkerProtocol.publish(file, command);
        commands.write(name); commands.newLine(); commands.flush();
        return file;
    }

    WorkerProtocol.Reply reply(Path file) throws Exception {
        Path reply = file.resolveSibling(file.getFileName()+".reply");
        if (!Files.exists(reply)) return null;
        return WorkerProtocol.JSON.readValue(reply.toFile(), WorkerProtocol.Reply.class);
    }

    void cancel(Path file) throws Exception {
        Files.write(file.resolveSibling(file.getFileName()+".cancel"), new byte[]{1});
    }

    void forget(Path file) throws IOException {
        for (String suffix : new String[]{"", ".reply", ".cancel"}) Files.deleteIfExists(file.resolveSibling(file.getFileName()+suffix));
    }

    synchronized void stop() throws Exception {
        if (process == null) return;
        long ownedPid = pid;
        long deadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.killMs);
        try {
            if (ownedPid > 1) {
                Process killer = new ProcessBuilder("/bin/kill", "-KILL", "--", "-"+ownedPid).start();
                if (!killer.waitFor(remainingMs(deadline), TimeUnit.MILLISECONDS)) { killer.destroyForcibly(); throw new IOException("Cannot signal owned worker session "+ownedPid); }
            }
            process.destroyForcibly();
            if (!process.waitFor(remainingMs(deadline), TimeUnit.MILLISECONDS)) throw new IOException("Worker leader did not exit: "+ownedPid);
            while (ownedPid > 1 && groupAlive(ownedPid)) {
                if (System.nanoTime() >= deadline) throw new IOException("Worker descendants still alive in session "+ownedPid);
                Thread.sleep(10);
            }
            System.err.println("worker_stopped generation="+generation+" pid="+ownedPid);
            if (commands != null) commands.close();
            process = null; commands = null; pid = 0;
            // Only this generation's uncommitted files; stable artifacts live elsewhere.
            try (java.util.stream.Stream<Path> files = Files.walk(home)) {
                for (Path path : (Iterable<Path>) files.sorted(java.util.Comparator.reverseOrder())::iterator) {
                    if (!path.equals(home) && !path.equals(home.resolve("worker.log"))) Files.deleteIfExists(path);
                }
            }
        } catch (Exception error) {
            throw new IOException("Worker termination unconfirmed; admission must remain closed", error);
        }
    }

    private static long remainingMs(long deadline) {
        return Math.max(1L, TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime()));
    }

    private static long processId(Process process) throws Exception {
        try { return ((Number)Process.class.getMethod("pid").invoke(process)).longValue(); }
        catch (NoSuchMethodException java8) {
            Field field = process.getClass().getDeclaredField("pid"); field.setAccessible(true);
            return ((Number)field.get(process)).longValue();
        }
    }

    static boolean groupAlive(long group) throws IOException {
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(Paths.get("/proc"), "[0-9]*")) {
            for (Path entry : entries) {
                try {
                    String stat = new String(Files.readAllBytes(entry.resolve("stat")), StandardCharsets.UTF_8);
                    String[] fields = stat.substring(stat.lastIndexOf(')')+2).split(" ");
                    if (Long.parseLong(fields[2]) == group && !"Z".equals(fields[0]) && !"X".equals(fields[0])) return true;
                } catch (NoSuchFileException gone) { /* Normal exit during enumeration. */ }
            }
        }
        return false;
    }
}
