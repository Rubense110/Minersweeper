import static spark.Spark.get;
import static spark.Spark.post;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Paths;
import java.util.Map;
import spark.Spark;

public class PromService {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static void main(String[] args) {
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
            if (!"alpha".equalsIgnoreCase(miner)) {
                res.status(400);
                res.type("application/json");
                return jsonError("invalid_request", "only miner=alpha is supported right now");
            }

            String pnml;
            try {
                pnml = AlphaMinerRunner.run(
                    Paths.get(env("LOGS_ROOT", "pm_site/pm_app/logs")),
                    logPath
                );
            } catch (Exception e) {
                res.status(500);
                res.type("application/json");
                return jsonError("mining_failed", e.getMessage());
            }

            res.status(200);
            res.type("application/xml");
            return pnml;
        });
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return (value == null || value.trim().isEmpty()) ? fallback : value;
    }

    private static String jsonError(String code, String message) {
        return String.format("{\"error\":\"%s\",\"message\":\"%s\"}",
            escape(code), escape(message));
    }

    private static String escape(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}

