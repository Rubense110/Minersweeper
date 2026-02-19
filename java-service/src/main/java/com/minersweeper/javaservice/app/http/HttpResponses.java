package com.minersweeper.javaservice.app.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import spark.Response;

final class HttpResponses {
    private HttpResponses() {}

    static String respondError(Response res, int status, String code, String message) {
        res.status(status);
        res.type("application/json");
        return jsonError(code, message);
    }

    static String respondJson(Response res, int status, Object payload, ObjectMapper mapper) throws Exception {
        res.status(status);
        res.type("application/json");
        return mapper.writeValueAsString(payload);
    }

    static String buildErrorMessage(Throwable error) {
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

    private static String jsonError(String code, String message) {
        return String.format("{\"error\":\"%s\",\"message\":\"%s\"}", escape(code), escape(message));
    }

    private static String escape(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
