package com.minersweeper.javaservice.app.http;

import java.util.Map;
import java.util.List;
import java.util.Arrays;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class OpenApiDocsTest {

    @Test
    public void buildSpecIncludesUsedEndpoints() {
        Map<String, Object> spec = OpenApiDocs.buildSpec("http://localhost:7070");

        assertEquals("3.1.0", spec.get("openapi"));

        @SuppressWarnings("unchecked")
        Map<String, Object> paths = (Map<String, Object>) spec.get("paths");
        assertTrue(paths.containsKey("/health"));
        assertTrue(paths.containsKey("/pipeline"));
        assertTrue(paths.containsKey("/artifacts/bulk"));
        assertTrue(paths.containsKey("/experiments/{experimentId}/cancel"));
        assertTrue(paths.containsKey("/experiments/{experimentId}/evaluations/{requestId}/cancel"));
        assertTrue(paths.containsKey("/experiments/{experimentId}/cleanup"));
    }

    @Test
    public void swaggerUiHtmlPointsToOpenApiEndpoint() {
        String html = OpenApiDocs.swaggerUiHtml("/openapi.json");

        assertTrue(html.contains("SwaggerUIBundle"));
        assertTrue(html.contains("/openapi.json"));
        assertTrue(html.contains("swagger-ui"));
    }

    @Test
    @SuppressWarnings("unchecked")
    public void v2ResponseSchemasRequireSemanticAndFeasibilityFields() {
        Map<String, Object> spec = OpenApiDocs.buildSpec("http://localhost:7070");
        Map<String, Object> components = (Map<String, Object>) spec.get("components");
        Map<String, Object> schemas = (Map<String, Object>) components.get("schemas");

        Map<String, Object> pipelineResponse = (Map<String, Object>) schemas.get("PipelineResponse");
        List<String> pipelineRequired = (List<String>) pipelineResponse.get("required");
        assertTrue(pipelineRequired.containsAll(Arrays.asList(
            "model_schema_version",
            "visible_transition_count",
            "is_feasible",
            "constraint_violations"
        )));

        Map<String, Object> artifactEntry = (Map<String, Object>) schemas.get("ArtifactEntry");
        List<String> artifactRequired = (List<String>) artifactEntry.get("required");
        assertTrue(artifactRequired.containsAll(Arrays.asList(
            "model_schema_version",
            "initial_marking",
            "final_marking",
            "final_markings",
            "transitions",
            "visible_transition_count",
            "is_feasible",
            "constraint_violations"
        )));

        Map<String, Object> transitionEntry = (Map<String, Object>) schemas.get("TransitionEntry");
        List<String> transitionRequired = (List<String>) transitionEntry.get("required");
        assertTrue(transitionRequired.containsAll(Arrays.asList("id", "invisible")));
    }
}
