package com.minersweeper.javaservice.app.validation;

import com.minersweeper.javaservice.api.dto.ArtifactBulkRequest;
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import java.util.Arrays;
import org.junit.Test;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class RequestValidatorTest {

    @Test
    public void pipelineRequestWithCanonicalMetricsIsAccepted() {
        PipelineRequest request = buildValidPipelineRequest(
            "fitness",
            "precision",
            "simplicity",
            "generalisation",
            "places",
            "transitions",
            "arcs",
            "cycl_complx",
            "ratio",
            "joins",
            "splits"
        );

        RequestValidator.validatePipelineRequest(request);

        assertNotNull(request.pipeline.preprocessing.parameters);
        assertNotNull(request.pipeline.miner.parameters);
        assertNotNull(request.excluded_miners);
    }

    @Test
    public void pipelineRequestRejectsUnsupportedMetric() {
        PipelineRequest request = buildValidPipelineRequest("fitness", "foo_metric");

        try {
            RequestValidator.validatePipelineRequest(request);
            fail("Expected BadRequestException for unsupported metric");
        } catch (BadRequestException expected) {
            assertTrue(expected.getMessage().contains("unsupported metric"));
        }
    }

    @Test
    public void pipelineRequestRejectsWrongCaseMetric() {
        PipelineRequest request = buildValidPipelineRequest("Fitness");

        try {
            RequestValidator.validatePipelineRequest(request);
            fail("Expected BadRequestException for non-canonical metric casing");
        } catch (BadRequestException expected) {
            assertTrue(expected.getMessage().contains("unsupported metric"));
        }
    }

    @Test
    public void pipelineRequestRejectsAliasMetric() {
        PipelineRequest request = buildValidPipelineRequest("precision_alignment");

        try {
            RequestValidator.validatePipelineRequest(request);
            fail("Expected BadRequestException for alias metric name");
        } catch (BadRequestException expected) {
            assertTrue(expected.getMessage().contains("unsupported metric"));
        }
    }

    @Test
    public void bulkRequestRejectsEmptyEvaluationId() {
        ArtifactBulkRequest request = new ArtifactBulkRequest();
        request.experiment_id = "run_001";
        request.evaluation_ids = Arrays.asList("ok-id", " ");
        request.include_pnml = Boolean.TRUE;

        try {
            RequestValidator.validateBulkArtifactsRequest(request);
            fail("Expected BadRequestException for blank evaluation id");
        } catch (BadRequestException expected) {
            assertTrue(expected.getMessage().contains("evaluation_ids cannot contain empty values"));
        }
    }

    private static PipelineRequest buildValidPipelineRequest(String... metrics) {
        PipelineRequest request = new PipelineRequest();
        request.experiment_id = "run_001";
        request.log_path = "/tmp/log.xes";
        request.metrics = Arrays.asList(metrics);

        PipelineRequest.PipelineConfig pipeline = new PipelineRequest.PipelineConfig();
        request.pipeline = pipeline;

        PipelineRequest.PreprocessingConfig preprocessing = new PipelineRequest.PreprocessingConfig();
        preprocessing.key = "matrix_filter";
        preprocessing.method = "Matrix Filtering";
        preprocessing.variant = "Conditional Probabilities (MF)";
        preprocessing.parameters = null;
        pipeline.preprocessing = preprocessing;

        PipelineRequest.MinerConfig miner = new PipelineRequest.MinerConfig();
        miner.key = "inductive";
        miner.family = "inductive";
        miner.variant = "Inductive Miner (IM)";
        miner.parameters = null;
        pipeline.miner = miner;

        return request;
    }
}
