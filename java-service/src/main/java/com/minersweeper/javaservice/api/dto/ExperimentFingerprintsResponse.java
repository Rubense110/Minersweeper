package com.minersweeper.javaservice.api.dto;

import java.util.ArrayList;
import java.util.List;

public class ExperimentFingerprintsResponse {
    public String experiment_id;
    public List<FingerprintEntry> fingerprints = new ArrayList<FingerprintEntry>();

    public static class FingerprintEntry {
        public String evaluation_id;
        public String fingerprint;
    }
}
