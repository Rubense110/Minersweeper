package com.minersweeper.javaservice.artifacts;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Stream;

public class ArtifactStore {
    private static final String DEFAULT_ROOT = "/tmp/minersweeper-artifacts";

    private final Path rootDir;
    private final ObjectMapper mapper;
    private final AtomicLong sequence = new AtomicLong(0L);

    public ArtifactStore(String rootDir) {
        this.rootDir = Paths.get(rootDir == null || rootDir.trim().isEmpty() ? DEFAULT_ROOT : rootDir).toAbsolutePath();
        this.mapper = new ObjectMapper();
    }

    public EvaluationResult store(
        PipelineRequest request,
        java.util.Map<String, Double> metrics,
        String pnml,
        String fingerprint
    ) throws IOException {
        String experimentId = request.experiment_id;
        String evaluationId = nextEvaluationId();
        Path experimentDir = ensureExperimentDir(experimentId);

        String pnmlFile = evaluationId + ".pnml";
        String metadataFile = evaluationId + ".json";
        Path pnmlPath = experimentDir.resolve(pnmlFile);
        Path metadataPath = experimentDir.resolve(metadataFile);

        Files.write(pnmlPath, pnml.getBytes(StandardCharsets.UTF_8));

        StoredArtifactMetadata metadata = new StoredArtifactMetadata();
        metadata.experiment_id = experimentId;
        metadata.evaluation_id = evaluationId;
        metadata.fingerprint = fingerprint;
        metadata.log_path = request.log_path;
        metadata.created_at_epoch_ms = System.currentTimeMillis();
        metadata.metrics = metrics;
        metadata.pipeline = request.pipeline;
        metadata.pnml_file = pnmlFile;
        mapper.writeValue(metadataPath.toFile(), metadata);

        return new EvaluationResult(experimentId, evaluationId, fingerprint, metrics);
    }

    public ArtifactBulkResponse readBulk(String experimentId, List<String> evaluationIds, boolean includePnml) throws IOException {
        ArtifactBulkResponse response = new ArtifactBulkResponse();
        response.experiment_id = experimentId;

        Path experimentDir = ensureExperimentDir(experimentId);
        for (String evaluationId : evaluationIds) {
            Path metadataPath = experimentDir.resolve(evaluationId + ".json");
            if (!Files.exists(metadataPath)) {
                throw new IllegalArgumentException("evaluation_id not found: " + evaluationId);
            }

            StoredArtifactMetadata metadata = mapper.readValue(metadataPath.toFile(), StoredArtifactMetadata.class);
            ArtifactBulkResponse.ArtifactEntry entry = new ArtifactBulkResponse.ArtifactEntry();
            entry.experiment_id = metadata.experiment_id;
            entry.evaluation_id = metadata.evaluation_id;
            entry.fingerprint = metadata.fingerprint;
            entry.log_path = metadata.log_path;
            entry.created_at_epoch_ms = metadata.created_at_epoch_ms;
            entry.metrics = metadata.metrics;
            entry.pipeline = metadata.pipeline;
            if (includePnml) {
                Path pnmlPath = experimentDir.resolve(metadata.pnml_file);
                if (!Files.exists(pnmlPath)) {
                    throw new IllegalArgumentException("PNML file not found for evaluation_id: " + evaluationId);
                }
                entry.pnml = new String(Files.readAllBytes(pnmlPath), StandardCharsets.UTF_8);
            }
            response.artifacts.add(entry);
        }
        return response;
    }

    public int cleanupExperiment(String experimentId) throws IOException {
        Path experimentDir = pathForExperiment(experimentId);
        if (!Files.exists(experimentDir)) {
            return 0;
        }

        List<Path> allPaths = new ArrayList<Path>();
        try (Stream<Path> stream = Files.walk(experimentDir)) {
            stream.sorted(Comparator.reverseOrder()).forEach(allPaths::add);
        }
        for (Path path : allPaths) {
            Files.deleteIfExists(path);
        }
        return allPaths.size();
    }

    private String nextEvaluationId() {
        long count = sequence.incrementAndGet();
        return System.currentTimeMillis() + "-" + count;
    }

    private Path ensureExperimentDir(String experimentId) throws IOException {
        Path experimentDir = pathForExperiment(experimentId);
        Files.createDirectories(experimentDir);
        return experimentDir;
    }

    private Path pathForExperiment(String experimentId) {
        return rootDir.resolve(sanitizeExperimentId(experimentId));
    }

    private static String sanitizeExperimentId(String experimentId) {
        if (experimentId == null || experimentId.trim().isEmpty()) {
            throw new IllegalArgumentException("experiment_id is required");
        }
        return experimentId.trim().replaceAll("[^a-zA-Z0-9._-]", "_");
    }
}
