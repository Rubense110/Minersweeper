package com.minersweeper.javaservice.app.http;

import java.util.Map;
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
        assertTrue(paths.containsKey("/experiments/{experimentId}/cleanup"));
    }

    @Test
    public void swaggerUiHtmlPointsToOpenApiEndpoint() {
        String html = OpenApiDocs.swaggerUiHtml("/openapi.json");

        assertTrue(html.contains("SwaggerUIBundle"));
        assertTrue(html.contains("/openapi.json"));
        assertTrue(html.contains("swagger-ui"));
    }
}
