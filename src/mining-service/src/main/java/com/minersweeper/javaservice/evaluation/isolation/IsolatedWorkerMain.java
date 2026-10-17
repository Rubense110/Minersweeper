package com.minersweeper.javaservice.evaluation.isolation;

import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Reused child JVM. Exactly one command is evaluated at a time. */
public final class IsolatedWorkerMain {
    public static void main(String[] args) throws Exception {
        com.minersweeper.javaservice.app.logging.UnknownExtensionLogFilter.install();
        System.setOut(System.err);
        Path home = Paths.get(args[0]);
        PromPipelineEvaluator evaluator = new PromPipelineEvaluator(new ArtifactStore(home.resolve("artifacts").toString()), Paths.get(args[1]));
        Files.write(home.resolve("ready"), new byte[]{1});
        try (BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            String name;
            while ((name = input.readLine()) != null) {
                final String commandName = name;
                Path commandFile = home.resolve(name);
                WorkerProtocol.Command command = WorkerProtocol.JSON.readValue(commandFile.toFile(), WorkerProtocol.Command.class);
                WorkerProtocol.Reply reply = new WorkerProtocol.Reply();
                AtomicBoolean finished = new AtomicBoolean();
                Thread cancellation = null;
                if (command.request != null) {
                    cancellation = new Thread(() -> {
                        while (!finished.get()) {
                            if (Files.exists(home.resolve(commandName+".cancel"))) {
                                evaluator.cancelEvaluation(command.request.experiment_id, command.request.request_id);
                                return;
                            }
                            try { Thread.sleep(20); } catch (InterruptedException stopped) { return; }
                        }
                    }, "evaluation-cancel-watch");
                    cancellation.setDaemon(true); cancellation.start();
                }
                boolean poisoned = false;
                try {
                    if ("cleanup".equals(command.operation)) evaluator.cleanupExperiment(command.experiment);
                    else reply.result = evaluator.evaluate(command.request);
                } catch (ExperimentCancelledException error) {
                    reply.code = "experiment_cancelled"; reply.message = error.toString();
                } catch (ReproducibilityException error) {
                    reply.code = error.code; reply.message = error.toString();
                } catch (IllegalArgumentException error) {
                    reply.code = "invalid_request"; reply.message = error.toString();
                } catch (Throwable error) {
                    error.printStackTrace(System.err);
                    poisoned = error instanceof Error;
                    reply.code = poisoned ? "worker_poisoned" : "evaluation_failed";
                    reply.message = error.toString();
                } finally {
                    finished.set(true);
                    if (cancellation != null) { cancellation.interrupt(); cancellation.join(); }
                    Thread.interrupted();
                }
                WorkerProtocol.publish(home.resolve(name+".reply"), reply);
                if (poisoned) return;
            }
        }
    }
}
