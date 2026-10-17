package com.minersweeper.javaservice.evaluation.isolation;

import com.minersweeper.javaservice.api.dto.*;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.ExperimentCancelledException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Stream;
import org.junit.Test;
import static org.junit.Assert.*;

public class WorkerPoolEvaluatorTest {
    private static PipelineRequest request(String id,String mode) {
        PipelineRequest r=new PipelineRequest();r.experiment_id="experiment";r.request_id=id;r.log_path=mode;
        r.metrics=Arrays.asList("fitness");return r;
    }
    private static WorkerPoolConfig config(int count,long timeout) {
        return new WorkerPoolConfig(count,"64m",timeout,40,5000,2000,2000,IsolatedWorkerFixture.class.getName());
    }
    private static void waitForHang(Path root) throws Exception {
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);
        while (System.nanoTime()<deadline) {
            try (Stream<Path> paths=Files.walk(root)) { if (paths.anyMatch(p->p.getFileName().toString().equals("hanging"))) return; }
            Thread.sleep(10);
        }
        fail("Fixture never began its uncooperative evaluation");
    }
    private static Throwable failed(Future<?> f) throws Exception {
        try { f.get(12,TimeUnit.SECONDS);fail("Expected failure");return null; }
        catch (ExecutionException e) { return e.getCause(); }
    }
    private static long pid(WorkerPoolEvaluator pool) {
        List<?> states=(List<?>)pool.health().get("worker_states");
        return ((Number)((Map<?,?>)states.get(0)).get("pid")).longValue();
    }
    @Test public void timeoutKillsWholeSessionAndPreservesOriginalArtifacts() throws Exception {
        Path root=Files.createTempDirectory("pool-recovery");ArtifactStore store=new ArtifactStore(root.resolve("stable").toString());
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(store,root,root.resolve("workers"),config(1,700))) {
            EvaluationResult before=pool.evaluate(request("before","ok"));long oldPid=pid(pool);
            try {pool.evaluate(request("blocked","hang"));fail("Expected timeout");}
            catch (WorkerPoolEvaluator.TaskFailure e) {assertEquals("evaluation_timeout",e.code);}
            assertFalse(WorkerProcess.groupAlive(oldPid));
            assertTrue(pool.terminationConfirmed("experiment","blocked"));
            EvaluationResult after=pool.evaluate(request("after","ok"));assertNotEquals(oldPid,pid(pool));
            assertNotEquals(before.evaluation_id,after.evaluation_id);
            ArtifactBulkResponse originals=store.readBulk("experiment",Arrays.asList(before.evaluation_id,after.evaluation_id),true);
            assertEquals(2,originals.artifacts.size());
            for (ArtifactBulkResponse.ArtifactEntry a:originals.artifacts) {
                assertEquals("<pnml>original-τ</pnml>",a.pnml);assertEquals(2,a.initial_marking.get(0).tokens);
                assertEquals(3,a.final_markings.get(0).get(0).tokens);assertEquals(2,a.final_markings.size());
                assertTrue(a.transitions.get(0).invisible);
            }
            try (Stream<Path> paths=Files.walk(root.resolve("stable"))) {assertEquals(2,paths.filter(p->p.toString().endsWith(".pnml")).count());}
            assertEquals(1L,pool.health().get("replacements"));
        }
    }
    @Test public void cancellingOneWorkerLeavesParallelEvaluationIntact() throws Exception {
        Path root=Files.createTempDirectory("pool-parallel");ExecutorService threads=Executors.newFixedThreadPool(2);
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(2,10000))) {
            Future<?> blocked=threads.submit(()->pool.evaluate(request("blocked","hang")));
            waitForHang(root);
            Future<EvaluationResult> good=threads.submit(()->pool.evaluate(request("good","slow")));
            pool.cancelEvaluation("experiment","blocked");
            assertTrue(failed(blocked) instanceof ExperimentCancelledException);
            assertEquals(.8,good.get(8,TimeUnit.SECONDS).metrics.get("fitness"),0);
            assertTrue(pool.terminationConfirmed("experiment","blocked"));
            assertNotNull(pool.evaluate(request("next","ok")));
        } finally {threads.shutdownNow();}
    }
    @Test public void duplicateRequestReturnsSameCommittedEvaluation() throws Exception {
        Path root=Files.createTempDirectory("pool-idempotent");ExecutorService threads=Executors.newFixedThreadPool(2);
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,3000))) {
            Future<EvaluationResult> a=threads.submit(()->pool.evaluate(request("same","slow")));
            Future<EvaluationResult> b=threads.submit(()->pool.evaluate(request("same","slow")));
            assertEquals(a.get(8,TimeUnit.SECONDS).evaluation_id,b.get(8,TimeUnit.SECONDS).evaluation_id);
            assertEquals(a.get().evaluation_id,pool.evaluate(request("same","slow")).evaluation_id);
        } finally {threads.shutdownNow();}
    }
    @Test public void queuedCancellationDoesNotRunOrConsumeActiveWorker() throws Exception {
        Path root=Files.createTempDirectory("pool-queue");ExecutorService threads=Executors.newFixedThreadPool(2);
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,10000))) {
            Future<?> blocked=threads.submit(()->pool.evaluate(request("running","hang")));waitForHang(root);
            Future<?> queued=threads.submit(()->pool.evaluate(request("queued","ok")));
            Thread.sleep(50);pool.cancelEvaluation("experiment","queued");
            assertTrue(failed(queued) instanceof ExperimentCancelledException);
            assertFalse(pool.terminationConfirmed("experiment","running"));
            pool.cancelExperiment("experiment");assertTrue(failed(blocked) instanceof ExperimentCancelledException);
            try {pool.evaluate(request("late","ok"));fail("Cancelled experiment accepted");}
            catch (ExperimentCancelledException expected) {}
        } finally {threads.shutdownNow();}
    }
    @Test public void startupFailureClosesAdmissionRatherThanPenalizingEveryModel() throws Exception {
        Path root=Files.createTempDirectory("pool-bad-start");
        WorkerPoolConfig bad=new WorkerPoolConfig(1,"64m",1000,10,1000,500,1000,"no.such.Worker");
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),bad)) {
            for (int i=0;i<2;i++) {
                try {pool.evaluate(request("bad"+i,"ok"));fail("Infrastructure should be unavailable");}
                catch (WorkerPoolEvaluator.Unavailable expected) {}
            }
            assertEquals("unavailable",pool.health().get("status"));
        }
    }
    @Test public void unexpectedWorkerExitIsInfrastructureFailureAndCapacityIsReplaced() throws Exception {
        Path root=Files.createTempDirectory("pool-crash");
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,1000))) {
            try {pool.evaluate(request("crash","exit"));fail("Expected crash");}
            catch (WorkerPoolEvaluator.Unavailable expected) {}
            assertNotNull(pool.evaluate(request("next","ok")));
        }
    }
    @Test public void cleanupRetiresExperimentButNotOtherExperiments() throws Exception {
        Path root=Files.createTempDirectory("pool-cleanup");
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,1000))) {
            pool.evaluate(request("first","ok"));pool.cleanupExperiment("experiment");
            try {pool.evaluate(request("late","ok"));fail("Closed experiment accepted");}catch(ExperimentCancelledException expected){}
            PipelineRequest another=request("other","ok");another.experiment_id="other";assertNotNull(pool.evaluate(another));
        }
    }
    @Test public void replacementFailureIsFatalInfrastructureAndNeverAnOrdinaryTimeout() throws Exception {
        Path root=Files.createTempDirectory("pool-replacement-fail");
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,500))) {
            try {pool.evaluate(request("bad","hang-and-break-replacement"));fail("Expected recovery failure");}
            catch (WorkerPoolEvaluator.Unavailable expected) {}
            assertEquals("unavailable",pool.health().get("status"));
        }
    }
    @Test public void cancellationBeforeArrivalIsConfirmedAndMismatchedDuplicateIsRejected() throws Exception {
        Path root=Files.createTempDirectory("pool-identities");
        try (WorkerPoolEvaluator pool=new WorkerPoolEvaluator(new ArtifactStore(root.resolve("stable").toString()),root,root.resolve("workers"),config(1,1000))) {
            pool.cancelEvaluation("experiment","never-started");
            assertTrue(pool.terminationConfirmed("experiment","never-started"));
            try {pool.evaluate(request("never-started","ok"));fail("Cancelled request accepted");}catch(ExperimentCancelledException expected){}
            pool.evaluate(request("same","ok"));
            try {pool.evaluate(request("same","slow"));fail("Mismatched duplicate accepted");}catch(IllegalArgumentException expected){}
        }
    }

}
