package com.minersweeper.javaservice.evaluation.isolation;

import com.minersweeper.javaservice.api.dto.*;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.*;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;

/** Stable coordinator: no XLog or plugin runs in this JVM. */
public final class WorkerPoolEvaluator implements PipelineEvaluator, AutoCloseable {
    public static class Unavailable extends Exception {
        public Unavailable(String message, Throwable cause) { super(message, cause); }
    }
    public static class TaskFailure extends Exception {
        public final String code;
        public TaskFailure(String code, String message) { super(message); this.code = code; }
    }
    private static final class Task {
        final String experiment;
        final com.fasterxml.jackson.databind.JsonNode request;
        final CompletableFuture<EvaluationResult> result = new CompletableFuture<EvaluationResult>();
        volatile boolean cancelled;
        Task(PipelineRequest request) { this.experiment = request.experiment_id; this.request=WorkerProtocol.JSON.valueToTree(request); }
    }
    private final WorkerPoolConfig config;
    private final ArtifactStore artifacts;
    private final List<WorkerProcess> workers = new ArrayList<WorkerProcess>();
    private final BlockingQueue<WorkerProcess> idle;
    private final Semaphore admission;
    private final Map<String,Task> tasks = new LinkedHashMap<String,Task>();
    private final Set<String> cancelledExperiments = new HashSet<String>();
    private final Set<String> cancelledRequests = new HashSet<String>();
    private volatile boolean closed;
    private volatile String unavailable;
    private final AtomicLong replacements = new AtomicLong();

    public WorkerPoolEvaluator(ArtifactStore artifacts, Path logsRoot, Path root, WorkerPoolConfig config) throws IOException {
        if (!Files.isDirectory(Paths.get("/proc")) || !Files.isExecutable(Paths.get("/bin/kill")))
            throw new IOException("Isolated evaluation currently requires Linux process sessions (/proc, setsid, /bin/kill)");
        this.artifacts = artifacts; this.config = config;
        Files.createDirectories(root);
        idle = new ArrayBlockingQueue<WorkerProcess>(config.workers);
        admission = new Semaphore(3*config.workers, true);
        for (int i=0; i<config.workers; i++) {
            WorkerProcess worker = new WorkerProcess(config, root, logsRoot);
            workers.add(worker); idle.add(worker);
        }
    }

    @Override public EvaluationResult evaluate(PipelineRequest request) throws Exception {
        if (request.request_id == null || request.request_id.trim().isEmpty()) request.request_id = UUID.randomUUID().toString();
        String key = key(request.experiment_id, request.request_id);
        Task task;
        boolean owner;
        synchronized (this) {
            checkAvailable();
            if (cancelledExperiments.contains(request.experiment_id) || cancelledRequests.contains(key))
                throw new ExperimentCancelledException("Evaluation cancelled before admission");
            task = tasks.get(key); owner = task == null;
            if (owner) { task = new Task(request); tasks.put(key, task); }
            else if (!task.request.equals(WorkerProtocol.JSON.valueToTree(request)))
                throw new IllegalArgumentException("request_id reused with a different payload");
        }
        if (!owner) return await(task);
        try {
            EvaluationResult result = execute(request, task);
            task.result.complete(result); return result;
        } catch (Exception error) {
            task.result.completeExceptionally(error); throw error;
        } finally {
            synchronized (this) {
                if (tasks.size() > 4096) {
                    Iterator<Map.Entry<String,Task>> entries = tasks.entrySet().iterator();
                    while (entries.hasNext() && tasks.size()>4096) if (entries.next().getValue().result.isDone()) entries.remove();
                }
            }
        }
    }

    private EvaluationResult execute(PipelineRequest request, Task task) throws Exception {
        if (!admission.tryAcquire()) throw new Unavailable("Isolated evaluation queue is full", null);
        WorkerProcess worker = null;
        boolean reusable = true;
        try {
            long deadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.queueMs);
            while (worker == null) {
                checkAvailable(); checkCancelled(task);
                worker = idle.poll(20, TimeUnit.MILLISECONDS);
                if (worker == null && System.nanoTime()>=deadline) throw new Unavailable("Isolated evaluator admission timed out", null);
            }
            try {
                worker.start(() -> task.cancelled || closed);
                cleanCaches(worker, task);
                checkCancelled(task);
                WorkerProtocol.Command command = new WorkerProtocol.Command(); command.request = request;
                Path file = worker.send(command);
                long executionDeadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.evaluationMs);
                WorkerProtocol.Reply reply = null;
                boolean timedOut = false;
                while (reply == null) {
                    if (task.cancelled || closed || System.nanoTime()>=executionDeadline) {
                        timedOut = !task.cancelled && !closed;
                        break;
                    }
                    reply = worker.reply(file);
                    if (reply == null && !worker.process.isAlive()) {
                        replace(worker, task);
                        throw new Unavailable("Isolated worker exited without a committed result; see worker log", null);
                    }
                    if (reply == null) Thread.sleep(10);
                }
                if (reply == null) {
                    worker.cancel(file);
                    long graceDeadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.graceMs);
                    while (worker.process.isAlive() && worker.reply(file)==null && System.nanoTime()<graceDeadline) Thread.sleep(10);
                    // Even a cooperative timeout response may leave plugin-global threads. Recycle this worker.
                    replace(worker, task);
                    if (timedOut) throw new TaskFailure("evaluation_timeout", "Evaluation exceeded "+config.evaluationMs+" ms; worker terminated and replaced");
                    throw new ExperimentCancelledException("Cancelled evaluation terminated");
                }
                worker.forget(file);
                if (task.cancelled || closed) { replace(worker, task); throw new ExperimentCancelledException("Cancelled before result commit"); }
                if ("worker_poisoned".equals(reply.code)) {
                    replace(worker, task);
                    throw new TaskFailure("evaluation_failed", reply.message);
                }
                if (reply.code != null) throw new TaskFailure(reply.code, reply.message);
                if (reply.result == null || !request.experiment_id.equals(reply.result.experiment_id)) throw new IOException("Invalid worker result identity");
                synchronized (this) {
                    checkCancelled(task);
                    artifacts.publishFrom(worker.home.resolve("artifacts"), reply.result.experiment_id, reply.result.evaluation_id);
                }
                return reply.result;
            } catch (ExperimentCancelledException error) {
                try { worker.stop(); }
                catch (Exception stopError) { unavailable="Cannot terminate cancelled worker"; throw new Unavailable(unavailable, stopError); }
                throw error;
            } catch (TaskFailure | Unavailable error) {
                throw error;
            } catch (Exception error) {
                try { worker.stop(); } catch (Exception stopError) { error.addSuppressed(stopError); }
                reusable = false;
                unavailable = "Isolated worker infrastructure failure";
                throw new Unavailable(unavailable, error);
            }
        } finally {
            if (worker != null && reusable && unavailable == null && !closed) idle.offer(worker);
            admission.release();
        }
    }

    private void replace(WorkerProcess worker, Task task) throws Unavailable {
        worker.recovering=true;
        try {
            worker.stop();
            replacements.incrementAndGet();
            // Do not resurrect a worker just to satisfy a cancelled experiment.
            if (!task.cancelled && !closed) worker.start(() -> task.cancelled || closed);
        } catch (ExperimentCancelledException cancelled) {
            // Startup already terminated its process before propagating cancellation.
        } catch (Exception error) {
            unavailable = "Cannot confirm worker termination/replacement";
            throw new Unavailable(unavailable, error);
        } finally { worker.recovering=false; }
    }

    private void cleanCaches(WorkerProcess worker, Task task) throws Exception {
        long deadline = System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.startupMs);
        for (String experiment : new ArrayList<String>(worker.pendingCleanup)) {
            checkCancelled(task);
            WorkerProtocol.Command command = new WorkerProtocol.Command(); command.operation="cleanup"; command.experiment=experiment;
            Path file = worker.send(command);
            WorkerProtocol.Reply reply;
            while ((reply=worker.reply(file)) == null) {
                checkCancelled(task);
                if (!worker.process.isAlive() || System.nanoTime()>=deadline) throw new IOException("Worker cache cleanup failed");
                Thread.sleep(10);
            }
            if (reply.code != null) throw new IOException("Worker cache cleanup: "+reply.message);
            worker.forget(file); worker.pendingCleanup.remove(experiment);
        }
    }

    private static EvaluationResult await(Task task) throws Exception {
        try { return task.result.get(); }
        catch (ExecutionException error) { Throwable cause=error.getCause(); if (cause instanceof Exception) throw (Exception)cause; throw new RuntimeException(cause); }
    }
    private void checkAvailable() throws Unavailable {
        if (closed || unavailable != null) throw new Unavailable(unavailable == null ? "Worker pool closed" : unavailable, null);
    }
    private static void checkCancelled(Task task) { if (task.cancelled) throw new ExperimentCancelledException("Evaluation cancelled"); }
    private static String key(String experiment, String request) { return experiment+"\u0000"+request; }

    @Override public synchronized void cancelEvaluation(String experiment, String request) {
        String key = key(experiment, request); cancelledRequests.add(key);
        Task task=tasks.get(key); if (task != null) task.cancelled=true;
    }
    @Override public synchronized void cancelExperiment(String experiment) {
        cancelledExperiments.add(experiment);
        for (Task task : tasks.values()) if (experiment.equals(task.experiment)) task.cancelled=true;
    }
    @Override public synchronized Boolean terminationConfirmed(String experiment, String request) {
        Task task=tasks.get(key(experiment,request));
        return task == null ? (cancelledRequests.contains(key(experiment,request)) ? Boolean.TRUE : null) : task.result.isDone() && unavailable == null;
    }
    @Override public synchronized void cleanupExperiment(String experiment) {
        for (Task task : tasks.values()) if (experiment.equals(task.experiment) && !task.result.isDone())
            throw new IllegalStateException("Cannot clean artifacts while evaluations are active");
        cancelledExperiments.add(experiment);
        for (WorkerProcess worker : workers) worker.pendingCleanup.add(experiment);
        tasks.entrySet().removeIf(e -> experiment.equals(e.getValue().experiment));
        cancelledRequests.removeIf(k -> k.startsWith(experiment+"\u0000"));
    }
    public synchronized Map<String,Object> health() {
        Map<String,Object> result = new LinkedHashMap<String,Object>();
        result.put("status", closed || unavailable != null ? "unavailable" : "ok");
        result.put("mode", "isolated-jvm-pool-v1"); result.put("workers",config.workers);
        result.put("available_workers",idle.size()); result.put("replacements",replacements.get());
        result.put("http_timeout_seconds",config.httpTimeoutSeconds()); result.put("evaluation_timeout_seconds",config.evaluationMs/1000.0);
        List<Map<String,Object>> states = new ArrayList<Map<String,Object>>();
        for (WorkerProcess worker : workers) {
            Map<String,Object> state = new LinkedHashMap<String,Object>();
            state.put("generation",worker.generation); state.put("pid",worker.pid);
            state.put("state",worker.recovering ? "recovering" : (idle.contains(worker) ? "available" : "busy"));
            states.add(state);
        }
        result.put("worker_states",states);
        result.put("worker_heap",config.heap); result.put("worker_processors",1);
        result.put("cancellation_grace_seconds",config.graceMs/1000.0);
        if (unavailable != null) result.put("error",unavailable);
        return result;
    }
    @Override public void close() throws Exception {
        synchronized (this) { closed=true; for (Task task:tasks.values()) task.cancelled=true; }
        // Active handlers own their worker until cleanup; wait a bounded time before shutdown sweep.
        long deadline=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(config.graceMs+config.killMs+1000);
        while (admission.availablePermits()!=3*config.workers && System.nanoTime()<deadline) Thread.sleep(10);
        for (WorkerProcess worker:workers) worker.stop();
    }
}
