package com.minersweeper.javaservice.artifacts;

import com.minersweeper.javaservice.api.dto.ArtifactBulkResponse;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.minersweeper.javaservice.api.dto.PipelineRequest;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class ArtifactStore {
    private static final String DEFAULT_ROOT = "/tmp/minersweeper-artifacts";

    private final Path rootDir;
    private final ObjectMapper mapper;

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
        return store(
            request,
            metrics,
            pnml,
            fingerprint,
            null,
            null,
            null,
            new ArrayList<String>(),
            new ArrayList<ArtifactBulkResponse.MarkingEntry>(),
            new ArrayList<ArtifactBulkResponse.MarkingEntry>(),
            new ArrayList<List<ArtifactBulkResponse.MarkingEntry>>(),
            new ArrayList<ArtifactBulkResponse.TransitionEntry>()
        );
    }

    public EvaluationResult store(
        PipelineRequest request,
        java.util.Map<String, Double> metrics,
        String pnml,
        String fingerprint,
        List<ArtifactBulkResponse.MarkingEntry> initialMarking,
        List<List<ArtifactBulkResponse.MarkingEntry>> finalMarkings
    ) throws IOException {
        return store(
            request,
            metrics,
            pnml,
            fingerprint,
            null,
            null,
            null,
            new ArrayList<String>(),
            initialMarking,
            new ArrayList<ArtifactBulkResponse.MarkingEntry>(),
            finalMarkings,
            new ArrayList<ArtifactBulkResponse.TransitionEntry>()
        );
    }

    public EvaluationResult store(
        PipelineRequest request,
        java.util.Map<String, Double> metrics,
        String pnml,
        String fingerprint,
        Integer modelSchemaVersion,
        List<ArtifactBulkResponse.MarkingEntry> initialMarking,
        List<ArtifactBulkResponse.MarkingEntry> finalMarking,
        List<List<ArtifactBulkResponse.MarkingEntry>> finalMarkings,
        List<ArtifactBulkResponse.TransitionEntry> transitions
    ) throws IOException {
        return store(
            request,
            metrics,
            pnml,
            fingerprint,
            modelSchemaVersion,
            null,
            null,
            new ArrayList<String>(),
            initialMarking,
            finalMarking,
            finalMarkings,
            transitions
        );
    }

    public EvaluationResult store(
        PipelineRequest request,
        java.util.Map<String, Double> metrics,
        String pnml,
        String fingerprint,
        Integer modelSchemaVersion,
        Integer visibleTransitionCount,
        Boolean isFeasible,
        List<String> constraintViolations,
        List<ArtifactBulkResponse.MarkingEntry> initialMarking,
        List<ArtifactBulkResponse.MarkingEntry> finalMarking,
        List<List<ArtifactBulkResponse.MarkingEntry>> finalMarkings,
        List<ArtifactBulkResponse.TransitionEntry> transitions
    ) throws IOException {
        String experimentId = request.experiment_id;
        String evaluationId = nextEvaluationId();
        Path experimentDir = ensureExperimentDir(experimentId);

        String pnmlFile = evaluationId + ".pnml";
        String metadataFile = evaluationId + ".json";
        Path pnmlPath = experimentDir.resolve(pnmlFile);
        Path metadataPath = experimentDir.resolve(metadataFile);

        StoredArtifactMetadata metadata = new StoredArtifactMetadata();
        metadata.experiment_id = experimentId;
        metadata.evaluation_id = evaluationId;
        metadata.fingerprint = fingerprint;
        metadata.log_path = request.log_path;
        metadata.created_at_epoch_ms = System.currentTimeMillis();
        metadata.metrics = metrics;
        metadata.metrics_status = Boolean.FALSE.equals(isFeasible) && metrics.isEmpty() ? "skipped_infeasible" : "computed";
        metadata.pipeline = request.pipeline;
        metadata.model_schema_version = modelSchemaVersion;
        metadata.visible_transition_count = visibleTransitionCount;
        metadata.is_feasible = isFeasible;
        metadata.constraint_violations = constraintViolations == null
            ? new ArrayList<String>()
            : constraintViolations;
        metadata.initial_marking = initialMarking == null
            ? new ArrayList<ArtifactBulkResponse.MarkingEntry>()
            : initialMarking;
        metadata.final_marking = finalMarking == null
            ? new ArrayList<ArtifactBulkResponse.MarkingEntry>()
            : finalMarking;
        metadata.final_markings = finalMarkings == null
            ? new ArrayList<List<ArtifactBulkResponse.MarkingEntry>>()
            : finalMarkings;
        metadata.transitions = transitions == null
            ? new ArrayList<ArtifactBulkResponse.TransitionEntry>()
            : transitions;
        metadata.pnml_file = pnmlFile;
        Path pnmlTemporary = Files.createTempFile(experimentDir, evaluationId, ".pnml.pending");
        Path metadataTemporary = null;
        boolean published = false;
        try {
            metadataTemporary = Files.createTempFile(experimentDir, evaluationId, ".json.pending");
            ExecutionChecks.check();
            Files.write(pnmlTemporary, pnml.getBytes(StandardCharsets.UTF_8));
            mapper.writeValue(metadataTemporary.toFile(), metadata);
            ExecutionChecks.check();
            publish(pnmlTemporary, pnmlPath);
            ExecutionChecks.check();
            // Metadata is the publication marker: a reader sees a complete pair.
            publish(metadataTemporary, metadataPath);
            published = true;
        } finally {
            Files.deleteIfExists(pnmlTemporary);
            if (metadataTemporary != null) Files.deleteIfExists(metadataTemporary);
            if (!published) {
                Files.deleteIfExists(metadataPath);
                Files.deleteIfExists(pnmlPath);
            }
        }

        return new EvaluationResult(
            experimentId, evaluationId, fingerprint, metrics,
            modelSchemaVersion, visibleTransitionCount, isFeasible, metadata.constraint_violations
        );
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
            entry.metrics_status = metadata.metrics_status;
            entry.pipeline = metadata.pipeline;
            entry.model_schema_version = metadata.model_schema_version;
            entry.visible_transition_count = metadata.visible_transition_count;
            entry.is_feasible = metadata.is_feasible;
            entry.constraint_violations = metadata.constraint_violations == null
                ? new ArrayList<String>()
                : metadata.constraint_violations;
            entry.initial_marking = metadata.initial_marking == null
                ? new ArrayList<ArtifactBulkResponse.MarkingEntry>()
                : metadata.initial_marking;
            entry.final_marking = metadata.final_marking == null
                ? new ArrayList<ArtifactBulkResponse.MarkingEntry>()
                : metadata.final_marking;
            entry.final_markings = metadata.final_markings == null
                ? new ArrayList<List<ArtifactBulkResponse.MarkingEntry>>()
                : metadata.final_markings;
            entry.transitions = metadata.transitions == null
                ? new ArrayList<ArtifactBulkResponse.TransitionEntry>()
                : metadata.transitions;
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

    private static void publish(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(source, target);
        }
    }

    private String nextEvaluationId() {
        return java.util.UUID.randomUUID().toString();
    }

    /** Commit an original pair from an isolated worker; never reconstruct its PNML. */
    public void publishFrom(Path stagingRoot, String experimentId, String evaluationId) throws IOException {
        if (evaluationId == null || !evaluationId.matches("[A-Za-z0-9-]+"))
            throw new IOException("Invalid isolated artifact identifier");
        ArtifactStore staging = new ArtifactStore(stagingRoot.toString());
        Path source = staging.pathForExperiment(experimentId);
        Path metadata = source.resolve(evaluationId+".json");
        String storedExperiment = null, storedEvaluation = null, pnmlFile = null;
        // Validate identity without materializing potentially large transition/marking arrays
        // in the coordinator just to copy an already serialized artifact.
        try (com.fasterxml.jackson.core.JsonParser parser = mapper.getFactory().createParser(metadata.toFile())) {
            if (parser.nextToken() != com.fasterxml.jackson.core.JsonToken.START_OBJECT) throw new IOException("Invalid artifact metadata");
            while (parser.nextToken() != com.fasterxml.jackson.core.JsonToken.END_OBJECT) {
                if (parser.currentToken() != com.fasterxml.jackson.core.JsonToken.FIELD_NAME) throw new IOException("Invalid metadata field");
                String field = parser.currentName(); parser.nextToken();
                if ("experiment_id".equals(field)) storedExperiment=parser.getValueAsString();
                else if ("evaluation_id".equals(field)) storedEvaluation=parser.getValueAsString();
                else if ("pnml_file".equals(field)) pnmlFile=parser.getValueAsString();
                parser.skipChildren();
            }
        }
        if (!experimentId.equals(storedExperiment) || !evaluationId.equals(storedEvaluation)
                || !(evaluationId+".pnml").equals(pnmlFile))
            throw new IOException("Isolated artifact identity mismatch");
        Path destination = ensureExperimentDir(experimentId);
        Path pnmlTemporary = Files.createTempFile(destination, evaluationId, ".pnml.pending");
        Path metadataTemporary = Files.createTempFile(destination, evaluationId, ".json.pending");
        boolean committed = false;
        try {
            Files.copy(source.resolve(pnmlFile), pnmlTemporary, StandardCopyOption.REPLACE_EXISTING);
            Files.copy(metadata, metadataTemporary, StandardCopyOption.REPLACE_EXISTING);
            publish(pnmlTemporary, destination.resolve(pnmlFile));
            publish(metadataTemporary, destination.resolve(evaluationId+".json"));
            committed = true;
        } finally {
            Files.deleteIfExists(pnmlTemporary); Files.deleteIfExists(metadataTemporary);
            if (!committed) {
                Files.deleteIfExists(destination.resolve(evaluationId+".json"));
                Files.deleteIfExists(destination.resolve(pnmlFile));
            }
        }
        try { Files.deleteIfExists(metadata); Files.deleteIfExists(source.resolve(pnmlFile)); }
        catch (IOException cleanup) { System.err.println("Committed artifact retained in staging: "+cleanup); }
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
