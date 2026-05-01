package com.minersweeper.javaservice.evaluation.fingerprint;

import java.util.Map;
import java.util.TreeMap;
import java.util.List;

import com.minersweeper.javaservice.api.dto.PipelineRequest;

public class FingerprintBuilder {
    
    public String buildFingerprint(PipelineRequest request) {
        StringBuilder builder = new StringBuilder();
        builder.append(safe(request.log_path)).append('|');
        builder.append(safe(request.conformance_mode)).append('|');
        builder.append(preprocessingFingerprint(request)).append('|');
        builder.append(safe(request.pipeline.miner.key)).append('|');
        builder.append(safe(request.pipeline.miner.variant)).append('|');
        builder.append(sortedMapString(request.pipeline.miner.parameters));
        return builder.toString();
    }

    private String preprocessingFingerprint(PipelineRequest request) {
        if (request == null || request.pipeline == null) {
            return "";
        }
        List<PipelineRequest.PreprocessingConfig> preprocessings = request.pipeline.preprocessings;
        if (preprocessings == null || preprocessings.isEmpty()) {
            PipelineRequest.PreprocessingConfig single = request.pipeline.preprocessing;
            if (single == null) {
                return "";
            }
            return singleFingerprint(single);
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < preprocessings.size(); i++) {
            if (i > 0) {
                out.append("||");
            }
            out.append(singleFingerprint(preprocessings.get(i)));
        }
        return out.toString();
    }

    private static String singleFingerprint(PipelineRequest.PreprocessingConfig preprocessing) {
        if (preprocessing == null) {
            return "";
        }
        return safe(preprocessing.key)
            + "~"
            + safe(preprocessing.variant)
            + "~"
            + sortedMapString(preprocessing.parameters);
    }

    private static String sortedMapString(Map<String, Object> map) {
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
