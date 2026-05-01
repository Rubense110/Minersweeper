package com.minersweeper.javaservice.evaluation.utils;

public class MetricUtils {
    
    public static double toDouble(Object value, double fallback) {
        if (value == null) {
            return fallback;
        }
        double parsed;
        if (value instanceof Number) {
            parsed = ((Number) value).doubleValue();
            return Double.isFinite(parsed) ? parsed : fallback;
        }
        try {
            parsed = Double.parseDouble(String.valueOf(value));
            return Double.isFinite(parsed) ? parsed : fallback;
        } catch (Exception ignored) {
            return fallback;
        }
    }

    public static double clamp01(double value) {
        if (!Double.isFinite(value)) {
            return 0.0;
        }
        if (value < 0.0) {
            return 0.0;
        }
        if (value > 1.0) {
            return 1.0;
        }
        return value;
    }

}
