package com.minersweeper.javaservice.app.logging;

public final class ServerErrorLogger {
    private ServerErrorLogger() {}

    public static void log(String code, Throwable error, boolean verboseExceptions) {
        if (verboseExceptions) {
            error.printStackTrace();
            return;
        }
        System.err.println("prom_service error [" + code + "]: " + buildErrorMessage(error));
    }

    private static String buildErrorMessage(Throwable error) {
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
}
