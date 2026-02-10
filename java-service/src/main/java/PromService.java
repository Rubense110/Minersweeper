import static spark.Spark.get;
import static spark.Spark.post;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import spark.Spark;

public class PromService {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Map<String, MinerRunner> RUNNERS = new HashMap<>();
    private static final ArtifactStore ARTIFACT_STORE = new ArtifactStore(env("ARTIFACTS_ROOT", "/tmp/minersweeper-artifacts"));
    private static final PipelineEvaluator PIPELINE_EVALUATOR = buildPipelineEvaluator();
    private static final boolean VERBOSE_EXCEPTIONS = Boolean.parseBoolean(env("PROM_VERBOSE_EXCEPTIONS", "false"));
    
    // Supported Miners
    static {
        RUNNERS.put("alpha", (logsRoot, logPath, variant, params) ->
            AlphaMinerRunner.run(logsRoot, logPath, variant)
        );
    }

    public static void main(String[] args) {
        installUnknownExtensionFilter();

        int port = Integer.parseInt(env("PORT", "7070"));
        Spark.port(port);
        System.out.println("prom_service: listening on port " + port);

        get("/health", (req, res) -> {
            res.type("application/json");
            return "{\"status\":\"ok\"}";
        });

        post("/mine", (req, res) -> {
            Map<String, Object> payload;
            try {
                payload = MAPPER.readValue(req.body(), Map.class);
            } catch (Exception e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_json", e.getMessage());
            }

            String logPath = (String) payload.get("log_path");
            String miner = (String) payload.get("miner");
            String variant = (String) payload.get("variant");
            if (variant == null) {
                variant = (String) payload.get("alpha_version");
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> params = (Map<String, Object>) payload.get("params");

            // Checks (No logs? No miner?)
            if (logPath == null || logPath.trim().isEmpty()) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", "log_path is required");
            }
            if (miner == null || miner.trim().isEmpty()) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", "miner is required");
            }

            // If miner, check if it is supported, in which case its respective class is called
            String minerKey = miner.trim().toLowerCase();
            MinerRunner runner = RUNNERS.get(minerKey);
            if (runner == null) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", "unsupported miner: " + miner);
            }

            // We try to discover a process model with the selected miner
            String pnml;
            try {
                pnml = runner.run(
                    Paths.get(env("LOGS_ROOT", "pm_site/pm_app/logs")),
                    logPath,
                    variant,
                    params
                );
            } catch (Exception e) {
                res.status(500);
                res.type("application/json");
                return jsonError("mining_failed", e.getMessage());
            }

            // Response (pmnl model discovered)
            res.status(200);
            res.type("application/xml");
            return pnml;
        });

        post("/pipeline", (req, res) -> {
            PipelineRequest payload;
            try {
                payload = MAPPER.readValue(req.body(), PipelineRequest.class);
                validatePipelineRequest(payload);
            } catch (BadRequestException e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", e.getMessage());
            } catch (Exception e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_json", e.getMessage());
            }

            try {
                EvaluationResult evaluation = PIPELINE_EVALUATOR.evaluate(payload);
                PipelineResponse response = new PipelineResponse(
                    evaluation.experiment_id,
                    evaluation.evaluation_id,
                    evaluation.fingerprint,
                    evaluation.metrics
                );
                res.status(200);
                res.type("application/json");
                return MAPPER.writeValueAsString(response);
            } catch (IllegalArgumentException e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", buildErrorMessage(e));
            } catch (Exception e) {
                logServerException("evaluation_failed", e);
                res.status(500);
                res.type("application/json");
                return jsonError("evaluation_failed", buildErrorMessage(e));
            }
        });

        post("/artifacts/bulk", (req, res) -> {
            ArtifactBulkRequest payload;
            try {
                payload = MAPPER.readValue(req.body(), ArtifactBulkRequest.class);
                validateBulkArtifactsRequest(payload);
            } catch (BadRequestException e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", e.getMessage());
            } catch (Exception e) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_json", e.getMessage());
            }

            try {
                boolean includePnml = payload.include_pnml == null || payload.include_pnml.booleanValue();
                ArtifactBulkResponse response = ARTIFACT_STORE.readBulk(payload.experiment_id, payload.evaluation_ids, includePnml);
                res.status(200);
                res.type("application/json");
                return MAPPER.writeValueAsString(response);
            } catch (IllegalArgumentException e) {
                res.status(404);
                res.type("application/json");
                return jsonError("not_found", e.getMessage());
            } catch (Exception e) {
                logServerException("artifact_read_failed", e);
                res.status(500);
                res.type("application/json");
                return jsonError("artifact_read_failed", buildErrorMessage(e));
            }
        });

        post("/experiments/:experimentId/cleanup", (req, res) -> {
            String experimentId = req.params(":experimentId");
            if (isBlank(experimentId)) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", "experimentId path parameter is required");
            }

            try {
                int deletedPaths = ARTIFACT_STORE.cleanupExperiment(experimentId);
                Map<String, Object> response = new LinkedHashMap<String, Object>();
                response.put("experiment_id", experimentId);
                response.put("deleted_paths", Integer.valueOf(deletedPaths));
                response.put("deleted", Boolean.valueOf(deletedPaths > 0));
                res.status(200);
                res.type("application/json");
                return MAPPER.writeValueAsString(response);
            } catch (Exception e) {
                logServerException("cleanup_failed", e);
                res.status(500);
                res.type("application/json");
                return jsonError("cleanup_failed", buildErrorMessage(e));
            }
        });
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return (value == null || value.trim().isEmpty()) ? fallback : value;
    }

    private static void installUnknownExtensionFilter() {
        PrintStream originalOut = System.out;
        PrintStream originalErr = System.err;
        System.setOut(new LineFilteringPrintStream(originalOut));
        System.setErr(new LineFilteringPrintStream(originalErr));
    }

    private static PipelineEvaluator buildPipelineEvaluator() {
        String mode = env("PIPELINE_EVALUATOR_MODE", "real").trim().toLowerCase();
        if ("stub".equals(mode)) {
            return new StubPipelineEvaluator(ARTIFACT_STORE);
        }
        return new PromPipelineEvaluator(
            ARTIFACT_STORE,
            Paths.get(env("LOGS_ROOT", "pm_site/pm_app/logs"))
        );
    }

    private static String jsonError(String code, String message) {
        return String.format("{\"error\":\"%s\",\"message\":\"%s\"}",
            escape(code), escape(message));
    }

    private static String escape(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String buildErrorMessage(Throwable error) {
        Throwable root = error;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }
        String message = root.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return root.getClass().getSimpleName();
        }
        return root.getClass().getSimpleName() + ": " + message;
    }

    private static void logServerException(String code, Throwable error) {
        if (VERBOSE_EXCEPTIONS) {
            error.printStackTrace();
            return;
        }
        System.err.println("prom_service error [" + code + "]: " + buildErrorMessage(error));
    }

    private static void validatePipelineRequest(PipelineRequest payload) {
        if (payload == null) {
            throw new BadRequestException("request body is required");
        }
        if (isBlank(payload.experiment_id)) {
            throw new BadRequestException("experiment_id is required");
        }
        if (isBlank(payload.log_path)) {
            throw new BadRequestException("log_path is required");
        }
        if (payload.pipeline == null) {
            throw new BadRequestException("pipeline is required");
        }
        if (payload.pipeline.preprocessing == null) {
            throw new BadRequestException("pipeline.preprocessing is required");
        }
        if (payload.pipeline.miner == null) {
            throw new BadRequestException("pipeline.miner is required");
        }
        if (isBlank(payload.pipeline.preprocessing.key)) {
            throw new BadRequestException("pipeline.preprocessing.key is required");
        }
        if (isBlank(payload.pipeline.miner.key)) {
            throw new BadRequestException("pipeline.miner.key is required");
        }
        if (payload.metrics == null || payload.metrics.isEmpty()) {
            throw new BadRequestException("metrics must contain at least one metric");
        }
        if (payload.pipeline.preprocessing.parameters == null) {
            payload.pipeline.preprocessing.parameters = new HashMap<String, Object>();
        }
        if (payload.pipeline.miner.parameters == null) {
            payload.pipeline.miner.parameters = new HashMap<String, Object>();
        }
        for (String metric : payload.metrics) {
            if (isBlank(metric)) {
                throw new BadRequestException("metrics cannot contain empty values");
            }
        }
    }

    private static void validateBulkArtifactsRequest(ArtifactBulkRequest payload) {
        if (payload == null) {
            throw new BadRequestException("request body is required");
        }
        if (isBlank(payload.experiment_id)) {
            throw new BadRequestException("experiment_id is required");
        }
        if (payload.evaluation_ids == null || payload.evaluation_ids.isEmpty()) {
            throw new BadRequestException("evaluation_ids must contain at least one value");
        }
        for (String evaluationId : payload.evaluation_ids) {
            if (isBlank(evaluationId)) {
                throw new BadRequestException("evaluation_ids cannot contain empty values");
            }
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private static final class LineFilteringPrintStream extends PrintStream {
        private final PrintStream delegate;

        private LineFilteringPrintStream(PrintStream delegate) {
            super(new LineFilteringOutputStream(delegate), true);
            this.delegate = delegate;
        }

        @Override
        public void close() {
            flush();
            // Keep underlying JVM streams open.
        }

        @Override
        public boolean checkError() {
            return delegate.checkError();
        }
    }

    private static final class LineFilteringOutputStream extends OutputStream {
        private static final String PREFIX = "Unknown extension:";
        private final PrintStream delegate;
        private final StringBuilder lineBuffer = new StringBuilder();

        private LineFilteringOutputStream(PrintStream delegate) {
            this.delegate = delegate;
        }

        @Override
        public synchronized void write(int b) throws IOException {
            if (b == '\n') {
                flushLine(true);
                return;
            }
            if (b != '\r') {
                lineBuffer.append((char) b);
            }
        }

        @Override
        public synchronized void flush() throws IOException {
            flushLine(false);
            delegate.flush();
        }

        private void flushLine(boolean withNewline) {
            if (lineBuffer.length() == 0) {
                if (withNewline) {
                    delegate.println();
                }
                return;
            }
            String line = lineBuffer.toString();
            lineBuffer.setLength(0);
            if (line.startsWith(PREFIX)) {
                return;
            }
            if (withNewline) {
                delegate.println(line);
            } else {
                delegate.print(line);
            }
        }
    }

    @FunctionalInterface
    private interface MinerRunner {
        String run(java.nio.file.Path logsRoot, String logPath, String variant, Map<String, Object> params)
            throws Exception;
    }

    private static final class BadRequestException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        private BadRequestException(String message) {
            super(Objects.requireNonNull(message, "message"));
        }
    }
}
