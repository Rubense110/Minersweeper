import static spark.Spark.get;
import static spark.Spark.post;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import spark.Spark;

public class PromService {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Map<String, MinerRunner> RUNNERS = new HashMap<>();
    
    // Supported Miners
    static {
        RUNNERS.put("alpha", (logsRoot, logPath, variant, params) ->
            AlphaMinerRunner.run(logsRoot, logPath, variant)
        );
    }

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

    @FunctionalInterface
    private interface MinerRunner {
        String run(java.nio.file.Path logsRoot, String logPath, String variant, Map<String, Object> params)
            throws Exception;
    }
}
