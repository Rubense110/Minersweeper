package com.minersweeper.javaservice.app.logging;

import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.util.regex.Pattern;

public final class UnknownExtensionLogFilter {
    private static volatile PrintStream originalOut = System.out;
    private static volatile PrintStream originalErr = System.err;

    private UnknownExtensionLogFilter() {}

    public static void install() {
        originalOut = System.out;
        originalErr = System.err;
        boolean suppressHeuristicsNoise = Boolean.parseBoolean(
            System.getenv("PROM_SUPPRESS_HEURISTICS_LOG_NOISE")
        );
        System.setOut(new LineFilteringPrintStream(originalOut, suppressHeuristicsNoise));
        System.setErr(new LineFilteringPrintStream(originalErr, suppressHeuristicsNoise));
    }

    public static PrintStream originalErr() {
        return originalErr;
    }

    private static final class LineFilteringPrintStream extends PrintStream {
        private final PrintStream delegate;

        private LineFilteringPrintStream(PrintStream delegate, boolean suppressHeuristicsNoise) {
            super(new LineFilteringOutputStream(delegate, suppressHeuristicsNoise), true);
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
        private static final Pattern MATRIX_SIZE = Pattern.compile("^\\s*\\d+\\s+x\\s+\\d+\\s+matrix\\s*$");
        private static final Pattern NUMERIC_ROW = Pattern.compile("^\\s*-?\\d+(?:\\.\\d+)?(?:\\s+-?\\d+(?:\\.\\d+)?)+\\s*$");
        private static final Pattern BOOLEAN_ROW = Pattern.compile("^\\s*(?:true|false|-1)(?:\\s+(?:true|false|-1))*\\s*$");
        private static final Pattern COLON_COUNT = Pattern.compile("^\\s*:\\s*\\d+\\s*$");
        private static final Pattern SIMPLE_MAP = Pattern.compile("^\\s*\\{[A-Za-z0-9_\\- ]+=\\d+(?:,\\s*[A-Za-z0-9_\\- ]+=\\d+)*\\}\\s*$");
        private static final Pattern STRUCTURAL_ROW = Pattern.compile("^[\\s\\d\\-\\.,\\[\\]]+$");
        private final PrintStream delegate;
        private final boolean suppressHeuristicsNoise;
        private final StringBuilder lineBuffer = new StringBuilder();

        private LineFilteringOutputStream(PrintStream delegate, boolean suppressHeuristicsNoise) {
            this.delegate = delegate;
            this.suppressHeuristicsNoise = suppressHeuristicsNoise;
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
            flushLine(false);
            delegate.flush();
        }

        private void flushLine(boolean withNewline) {
            if (lineBuffer.length() == 0) {
                if (withNewline && !suppressHeuristicsNoise) {
                    delegate.println();
                }
                return;
            }
            String line = lineBuffer.toString();
            lineBuffer.setLength(0);
            if (shouldSuppress(line)) {
                return;
            }
            if (withNewline) {
                delegate.println(line);
            } else {
                delegate.print(line);
            }
        }

        private boolean shouldSuppress(String line) {
            if (line.startsWith(PREFIX)) {
                return true;
            }
            if (!suppressHeuristicsNoise) {
                return false;
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
            for (String prefix : HEURISTICS_PREFIXES) {
                if (line.startsWith(prefix)) {
                    return true;
                }
            }
            return false;
        }
    }
}
