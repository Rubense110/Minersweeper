package com.minersweeper.javaservice.evaluation.fingerprint;

import java.util.Map;
import java.util.TreeMap;

import com.minersweeper.javaservice.api.dto.PipelineRequest;

public class FingerprintBuilder {
    
    public String buildFingerprint(PipelineRequest request) {
        StringBuilder builder = new StringBuilder();
        builder.append(safe(request.log_path)).append('|');
        builder.append(safe(request.conformance_mode)).append('|');
        builder.append(safe(request.pipeline.preprocessing.key)).append('|');
        builder.append(safe(request.pipeline.preprocessing.variant)).append('|');
        builder.append(sortedMapString(request.pipeline.preprocessing.parameters)).append('|');
        builder.append(safe(request.pipeline.miner.key)).append('|');
        builder.append(safe(request.pipeline.miner.variant)).append('|');
        builder.append(sortedMapString(request.pipeline.miner.parameters));
        return builder.toString();
    }

    private String sortedMapString(Map<String, Object> map) {
        if (map == null || map.isEmpty()) {
            return "{}";
        }
        TreeMap<String, Object> sorted = new TreeMap<String, Object>(map);
        return sorted.toString();
    }

    private static String safe(String value) {
        return value == null ? "" : value.trim();
    }
}
