package com.minersweeper.javaservice.app.logging;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.regex.Pattern;

public final class UnknownExtensionLogFilter {
    private static volatile PrintStream originalOut = System.out;
    private static volatile PrintStream originalErr = System.err;
    private static final String SERVICE_PREFIX = "[prom_service] ";
    private static final DateTimeFormatter TIMESTAMP_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss,SSS");
    private static final boolean SUPPRESS_PROM_NOISE = resolvePromNoiseSuppression();

    private UnknownExtensionLogFilter() {}

    public static void install() {
        PrintStream baseOut = System.out;
        PrintStream baseErr = System.err;
        PrintStream fileSink = buildFileSink(baseErr);
        if (fileSink != null) {
            baseOut = new PrintStream(new TeeOutputStream(baseOut, fileSink), true);
            baseErr = new PrintStream(new TeeOutputStream(baseErr, fileSink), true);
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                try {
                    fileSink.flush();
                    fileSink.close();
                } catch (Exception ignored) {
                    // Ignore shutdown close failures.
                }
            }, "prom-log-file-closer"));
        }

        originalOut = baseOut;
        originalErr = baseErr;
        System.setOut(new LineFilteringPrintStream(originalOut));
        System.setErr(new LineFilteringPrintStream(originalErr));
    }

    public static PrintStream originalErr() {
        return originalErr;
    }

    static boolean shouldSuppressPromNoiseLine(String line) {
        return LineFilteringOutputStream.shouldSuppressLine(line, true);
    }

    private static PrintStream buildFileSink(PrintStream fallbackErr) {
        if (!Boolean.parseBoolean(env("PROM_LOG_TO_FILE", "false"))) {
            return null;
        }
        String rawPath = env("PROM_LOG_FILE", "").trim();
        if (rawPath.isEmpty()) {
            fallbackErr.println("prom_service: PROM_LOG_TO_FILE=true but PROM_LOG_FILE is empty; file logging disabled");
            return null;
        }
        Path logPath = Paths.get(rawPath).toAbsolutePath().normalize();
        Path parent = logPath.getParent();
        try {
            if (parent != null) {
                Files.createDirectories(parent);
            }
            return new PrintStream(new FileOutputStream(logPath.toFile(), true), true, StandardCharsets.UTF_8.name());
        } catch (Exception error) {
            fallbackErr.println(
                "prom_service: failed to initialize PROM_LOG_FILE=" + logPath + " (" + error.getClass().getSimpleName() + ": " + error.getMessage() + ")"
            );
            return null;
        }
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value;
    }

    private static boolean parseBooleanEnv(String key, boolean fallback) {
        return Boolean.parseBoolean(env(key, Boolean.toString(fallback)));
    }

    private static boolean resolvePromNoiseSuppression() {
        String explicit = System.getenv("PROM_SUPPRESS_PROM_NOISE");
        if (explicit != null && !explicit.trim().isEmpty()) {
            return Boolean.parseBoolean(explicit);
        }
        return parseBooleanEnv("PROM_SUPPRESS_SPLIT_MINER_NOISE", true);
    }

    private static final class TeeOutputStream extends OutputStream {
        private final OutputStream first;
        private final OutputStream second;

        private TeeOutputStream(OutputStream first, OutputStream second) {
            this.first = first;
            this.second = second;
        }

        @Override
        public synchronized void write(int b) throws IOException {
            first.write(b);
            second.write(b);
        }

        @Override
        public synchronized void write(byte[] b, int off, int len) throws IOException {
            first.write(b, off, len);
            second.write(b, off, len);
        }

        @Override
        public synchronized void flush() throws IOException {
            first.flush();
            second.flush();
        }

        @Override
        public void close() throws IOException {
            flush();
        }
    }

    private static final class LineFilteringPrintStream extends PrintStream {
        private final PrintStream delegate;

        private LineFilteringPrintStream(PrintStream delegate) {
            super(new LineFilteringOutputStream(delegate), true);
            this.delegate = delegate;
        }

        @Override
        public void close() {
            flush();
            // Keep underlying JVM streams open.
        }

        @Override
        public boolean checkError() {
            return delegate.checkError();
        }
    }

    private static final class LineFilteringOutputStream extends OutputStream {
        private static final String PREFIX = "Unknown extension:";
        private static final String TOOLBOX_PREFIX = "[Toolbox]";
        private static final String LIFE_CYCLE_REPAIR_MESSAGE = "life cycle repair not yet implemented";
        private static final String UNMATCHED_MESSAGE = "unmatched";
        private static final String EVAL_MARKER = "[EVAL]";
        private static final String[] HEURISTICS_PREFIXES = new String[] {
            "Event classes defined by Event Name",
            "Best Start:",
            "Best End:",
            "Connections Number:",
            "Noise:",
            "Events Number:",
            "Traces Number:",
            "Instances Number:",
            "Long Range Succession Count",
            "Long Range Dependency Measures",
            "L1L Dependency Measures All",
            "And In Measures All",
            "And Out Measures All",
            "L2L Dependency Measures All",
            "AB Dependency Measures All",
            "Dependency Measures Accepted",
            "Noise Counters",
            "Event Counter",
            "Start Counter",
            "End Counter",
            "Direct Succession Counter",
            "Succession 2 Counter",
            "L1L Relation",
            "L2L Relation",
            "Best Input Measure",
            "Best Output Measure",
            "Best Input Event",
            "Best Output Event",
            "Input Set",
            "Output Set",
            "==== Activities Mapping Part",
            "Reverse Activities Mapping",
            "Element ",
            "In:",
            "Out:",
            "Relative to Best Threshold",
            "Positive Observation Threshold",
            "Dependency Threshold",
            "L1L Threshold",
            "L2L Threshold",
            "Long Distance Threshold",
            "Dependency Divisor",
            "AND Threshold",
            "Check Best Against L2L",
            "Mining Time:",
            "Annotating Time:",
            "Outputs of ",
            "Inputs of ",
            "--x--"
        };
        private static final String[] SPLIT_MINER_NOISE_MARKERS = new String[] {
            "split task:",
            "discovering relations",
            "double relation for:",
            "low frequency observations",
            "skipcounter =",
            "total potential concurrencies",
            "removed parallelism edges",
            "loop-back outgoing edge",
            "potential parallelisms",
            "max parallelisms allowed",
            "event subprocesses",
            "pair (",
            "fwd removed:",
            "bkw removed:",
            "not removable!",
            "printing parallelisms"
        };
        private static final Pattern MATRIX_SIZE = Pattern.compile("^\\s*\\d+\\s+x\\s+\\d+\\s+matrix\\s*$");
        private static final Pattern NUMERIC_ROW = Pattern.compile("^\\s*-?\\d+(?:\\.\\d+)?(?:\\s+-?\\d+(?:\\.\\d+)?)+\\s*$");
        private static final Pattern BOOLEAN_ROW = Pattern.compile("^\\s*(?:true|false|-1)(?:\\s+(?:true|false|-1))*\\s*$");
        private static final Pattern COLON_COUNT = Pattern.compile("^\\s*:\\s*\\d+\\s*$");
        private static final Pattern SIMPLE_MAP = Pattern.compile("^\\s*\\{[A-Za-z0-9_\\- ]+=\\d+(?:,\\s*[A-Za-z0-9_\\- ]+=\\d+)*\\}\\s*$");
        private static final Pattern STRUCTURAL_ROW = Pattern.compile("^[\\s\\d\\-\\.,\\[\\]]+$");
        private static final Pattern QUEUE_STATUS_ROW = Pattern.compile("^\\s*(?:Accepted|Completed|Queued)(?:\\s+(?:Accepted|Completed|Queued))*\\s*$");
        private static final String LIFECYCLE_SEGMENT = "[A-Za-z][A-Za-z0-9]*(?:(?:\\s+-\\s+|\\s+)[A-Za-z0-9][A-Za-z0-9]*)*";
        private static final Pattern LIFECYCLE_TRACE_ENTRY = Pattern.compile("^" + LIFECYCLE_SEGMENT + "\\+" + LIFECYCLE_SEGMENT + "$");
        private static final Pattern SCORE_SUFFIX = Pattern.compile("^-?\\d+(?:\\.\\d+)?$");
        private static final Pattern ANSI_ESCAPE = Pattern.compile("\\u001B\\[[;\\d]*m");
        private final PrintStream delegate;
        private final StringBuilder lineBuffer = new StringBuilder();

        private LineFilteringOutputStream(PrintStream delegate) {
            this.delegate = delegate;
        }

        @Override
        public synchronized void write(int b) throws IOException {
            if (b == '\n') {
                flushLine(true);
                return;
            }
            if (b != '\r') {
                lineBuffer.append((char) b);
            }
        }

        @Override
        public synchronized void flush() throws IOException {
            flushLine(true);
            delegate.flush();
        }

        private void flushLine(boolean withNewline) {
            if (lineBuffer.length() == 0) {
                return;
            }
            String line = lineBuffer.toString();
            lineBuffer.setLength(0);
            if (shouldSuppress(line)) {
                return;
            }
            String taggedLine = "[" + LocalDateTime.now().format(TIMESTAMP_FORMAT) + "] " + SERVICE_PREFIX + line;
            if (withNewline) {
                delegate.println(taggedLine);
            } else {
                delegate.print(taggedLine);
            }
        }

        private static boolean shouldSuppressLine(String line, boolean suppressPromNoise) {
            if (!suppressPromNoise) {
                return false;
            }
            if (line.startsWith(PREFIX)) {
                return true;
            }
            if (line.startsWith(TOOLBOX_PREFIX)) {
                return true;
            }
            String normalized = line.trim().toLowerCase();
            if (normalized.contains(LIFE_CYCLE_REPAIR_MESSAGE)) {
                return true;
            }
            if (normalized.equals(UNMATCHED_MESSAGE)) {
                return true;
            }
            if (isSplitMinerNoise(line, normalized)) {
                return true;
            }
            if (line.trim().isEmpty()) {
                return true;
            }
            if (line.contains("#/trace")) {
                return true;
            }
            if (line.equals("None")) {
                return true;
            }
            if (MATRIX_SIZE.matcher(line).matches()) {
                return true;
            }
            if (NUMERIC_ROW.matcher(line).matches()) {
                return true;
            }
            if (BOOLEAN_ROW.matcher(line).matches()) {
                return true;
            }
            if (COLON_COUNT.matcher(line).matches()) {
                return true;
            }
            if (SIMPLE_MAP.matcher(line).matches()) {
                return true;
            }
            if (STRUCTURAL_ROW.matcher(line).matches()) {
                return true;
            }
            if (QUEUE_STATUS_ROW.matcher(line).matches()) {
                return true;
            }
            if (isLifecycleTraceScoreRow(line)) {
                return true;
            }
            for (String prefix : HEURISTICS_PREFIXES) {
                if (line.startsWith(prefix)) {
                    return true;
                }
            }
            return false;
        }

        private boolean shouldSuppress(String line) {
            return shouldSuppressLine(line, SUPPRESS_PROM_NOISE);
        }

        private static boolean isSplitMinerNoise(String line, String normalized) {
            if (line.contains(EVAL_MARKER)) {
                return false;
            }
            String normalizedCore = normalizeCoreLine(normalized);
            if (normalizedCore.contains(EVAL_MARKER.toLowerCase())) {
                return false;
            }
            if (normalizedCore.startsWith("dfgp - ")) {
                return true;
            }
            if (normalizedCore.startsWith("info - log parsed at ")) {
                return true;
            }
            if (normalizedCore.equals("lpsolve libraries loaded")) {
                return true;
            }
            if (!(normalizedCore.startsWith("debug -") || normalizedCore.startsWith("warning -"))) {
                return false;
            }
            for (String marker : SPLIT_MINER_NOISE_MARKERS) {
                if (normalizedCore.contains(marker)) {
                    return true;
                }
            }
            return false;
        }

        private static String normalizeCoreLine(String normalizedLowercase) {
            String current = ANSI_ESCAPE.matcher(normalizedLowercase).replaceAll("").trim();
            while (current.startsWith("[")) {
                int close = current.indexOf(']');
                if (close < 0) {
                    break;
                }
                current = current.substring(close + 1).trim();
            }
            return current;
        }

        private static boolean isLifecycleTraceScoreRow(String line) {
            String trimmed = line.trim();
            if (!trimmed.startsWith("[") || trimmed.indexOf(']') < 0) {
                return false;
            }
            int closingBracket = trimmed.lastIndexOf(']');
            if (closingBracket <= 0 || closingBracket == trimmed.length() - 1) {
                return false;
            }
            String score = trimmed.substring(closingBracket + 1).trim();
            if (!SCORE_SUFFIX.matcher(score).matches()) {
                return false;
            }
            String rawTrace = trimmed.substring(1, closingBracket).trim();
            if (rawTrace.isEmpty()) {
                return false;
            }
            String[] entries = rawTrace.split("\\s*,\\s*");
            for (String entry : entries) {
                if (!LIFECYCLE_TRACE_ENTRY.matcher(entry).matches()) {
                    return false;
                }
            }
            return true;
        }
    }
}
