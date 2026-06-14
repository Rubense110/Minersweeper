package com.minersweeper.javaservice.app.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.ExperimentCancelledException;
import com.minersweeper.javaservice.evaluation.PipelineEvaluator;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class PromHttpHandlersTest {

    @Test
    public void handlePipelineReturnsInvalidJsonForMalformedBody() throws Exception {
        PromHttpHandlers handlers = new PromHttpHandlers(
            new ObjectMapper(),
            new NoopPipelineEvaluator(),
            new ArtifactStore(Files.createTempDirectory("http-handlers-invalid-json").toString()),
            false
        );

        FakeResponse response = new FakeResponse();
        Object payload = handlers.handlePipeline(new FakeRequest("{"), response);

        assertEquals(400, response.status());
        assertEquals("application/json", response.type());
        assertTrue(String.valueOf(payload).contains("\"error\":\"invalid_json\""));
    }

    @Test
    public void handlePipelineMapsCancellationToConflict() throws Exception {
        PromHttpHandlers handlers = new PromHttpHandlers(
            new ObjectMapper(),
            new PipelineEvaluator() {
                @Override
                public EvaluationResult evaluate(com.minersweeper.javaservice.api.dto.PipelineRequest request) throws Exception {
                    throw new ExperimentCancelledException("experiment cancelled");
                }

                @Override
                public void cancelExperiment(String experimentId) {}

                @Override
                public void cleanupExperiment(String experimentId) {}
            },
            new ArtifactStore(Files.createTempDirectory("http-handlers-cancelled").toString()),
            false
        );

        FakeResponse response = new FakeResponse();
        Object payload = handlers.handlePipeline(new FakeRequest(validPipelineJson()), response);

        assertEquals(409, response.status());
        assertEquals("application/json", response.type());
        assertTrue(String.valueOf(payload).contains("\"error\":\"experiment_cancelled\""));
    }

    @Test
    public void handleArtifactsBulkMapsMissingEvaluationToNotFound() throws Exception {
        Path tmp = Files.createTempDirectory("http-handlers-artifacts");
        PromHttpHandlers handlers = new PromHttpHandlers(
            new ObjectMapper(),
            new NoopPipelineEvaluator(),
            new ArtifactStore(tmp.toString()),
            false
        );

        FakeResponse response = new FakeResponse();
        Object payload = handlers.handleArtifactsBulk(
            new FakeRequest("{\"experiment_id\":\"run_1\",\"evaluation_ids\":[\"missing\"],\"include_pnml\":true}"),
            response
        );

        assertEquals(404, response.status());
        assertEquals("application/json", response.type());
        assertTrue(String.valueOf(payload).contains("\"error\":\"not_found\""));
    }

    @Test
    public void handleCleanupReturnsDeletedMetadata() throws Exception {
        final String[] cleanedExperiment = new String[1];
        PromHttpHandlers handlers = new PromHttpHandlers(
            new ObjectMapper(),
            new PipelineEvaluator() {
                @Override
                public EvaluationResult evaluate(com.minersweeper.javaservice.api.dto.PipelineRequest request) {
                    return null;
                }

                @Override
                public void cancelExperiment(String experimentId) {}

                @Override
                public void cleanupExperiment(String experimentId) {
                    cleanedExperiment[0] = experimentId;
                }
            },
            new ArtifactStore(Files.createTempDirectory("http-handlers-cleanup").toString()),
            false
        );

        FakeResponse response = new FakeResponse();
        Object payload = handlers.handleCleanup(new FakeRequest("", "run_cleanup"), response);

        assertEquals(200, response.status());
        assertEquals("application/json", response.type());
        assertEquals("run_cleanup", cleanedExperiment[0]);
        assertTrue(String.valueOf(payload).contains("\"experiment_id\":\"run_cleanup\""));
        assertTrue(String.valueOf(payload).contains("\"deleted_paths\":0"));
    }

    private static String validPipelineJson() {
        return "{"
            + "\"experiment_id\":\"run_1\","
            + "\"log_path\":\"/tmp/log.xes\","
            + "\"pipeline\":{"
            +   "\"preprocessing\":{\"key\":\"matrix_filter\",\"method\":\"Matrix Filtering\",\"variant\":\"Conditional Probabilities (MF)\",\"parameters\":{}},"
            +   "\"miner\":{\"key\":\"inductive\",\"family\":\"inductive\",\"variant\":\"Inductive Miner (IM)\",\"parameters\":{}}"
            + "},"
            + "\"metrics\":[\"fitness\"]"
            + "}";
    }

    private static final class NoopPipelineEvaluator implements PipelineEvaluator {
        @Override
        public EvaluationResult evaluate(com.minersweeper.javaservice.api.dto.PipelineRequest request) {
            Map<String, Double> metrics = new LinkedHashMap<String, Double>();
            metrics.put("fitness", Double.valueOf(1.0));
            return new EvaluationResult("run_1", "eval_1", "fp_1", metrics);
        }

        @Override
        public void cancelExperiment(String experimentId) {}

        @Override
        public void cleanupExperiment(String experimentId) {}
    }

    private static final class FakeRequest extends spark.Request {
        private final String body;
        private final Map<String, String> params;

        FakeRequest(String body) {
            this(body, null);
        }

        FakeRequest(String body, String experimentId) {
            super();
            this.body = body;
            this.params = new LinkedHashMap<String, String>();
            if (experimentId != null) {
                this.params.put(":experimentId", experimentId);
            }
        }

        @Override
        public String body() {
            return body;
        }

        @Override
        public String params(String param) {
            return params.get(param);
        }

        @Override
        public Map<String, String> params() {
            return Collections.unmodifiableMap(params);
        }
    }

    private static final class FakeResponse extends spark.Response {
        private int status;
        private String type;

        FakeResponse() {
            super();
        }

        @Override
        public void status(int statusCode) {
            this.status = statusCode;
        }

        @Override
        public int status() {
            return status;
        }

        @Override
        public void type(String contentType) {
            this.type = contentType;
        }

        @Override
        public String type() {
            return type;
        }
    }
}
