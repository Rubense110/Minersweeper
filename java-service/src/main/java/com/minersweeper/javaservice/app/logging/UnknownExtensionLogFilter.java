package com.minersweeper.javaservice.app.logging;

import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;

public final class UnknownExtensionLogFilter {
    private UnknownExtensionLogFilter() {}

    public static void install() {
        PrintStream originalOut = System.out;
        PrintStream originalErr = System.err;
        System.setOut(new LineFilteringPrintStream(originalOut));
        System.setErr(new LineFilteringPrintStream(originalErr));
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
            flushLine(false);
            delegate.flush();
        }

        private void flushLine(boolean withNewline) {
            if (lineBuffer.length() == 0) {
                if (withNewline) {
                    delegate.println();
                }
                return;
            }
            String line = lineBuffer.toString();
            lineBuffer.setLength(0);
            if (line.startsWith(PREFIX)) {
                return;
            }
            if (withNewline) {
                delegate.println(line);
            } else {
                delegate.print(line);
            }
        }
    }
}
