package com.minersweeper.javaservice.evaluation.utils;

public class TextUtils {
    
    public static String safe(String value) {
        return value == null ? "" : value.trim();
    }

    public static String safeObj(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    public static String safeOrDefault(Object value, String fallback) {
        String text = value == null ? "" : String.valueOf(value).trim();
        return text.isEmpty() ? fallback : text;
    }

}
