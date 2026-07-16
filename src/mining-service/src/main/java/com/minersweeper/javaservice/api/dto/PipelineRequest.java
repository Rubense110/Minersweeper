package com.minersweeper.javaservice.api.dto;

import java.util.List;
import java.util.Map;

public class PipelineRequest {
    public String experiment_id;
    public String request_id;
    public String log_path;
    public String conformance_mode;
    public PipelineConfig pipeline;
    public List<String> metrics;
    public List<String> excluded_miners;

    public static class PipelineConfig {
        public PreprocessingConfig preprocessing;
        public List<PreprocessingConfig> preprocessings;
        public MinerConfig miner;
    }

    public static class PreprocessingConfig {
        public String key;
        public String method;
        public String variant;
        public Map<String, Object> parameters;
    }

    public static class MinerConfig {
        public String key;
        public String family;
        public String variant;
        public Map<String, Object> parameters;
    }
}
