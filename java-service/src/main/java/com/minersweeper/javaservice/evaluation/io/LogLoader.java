package com.minersweeper.javaservice.evaluation.io;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;

public class LogLoader {
    private final Path logsRoot;

    public LogLoader(Path logsRoot) {
        this.logsRoot = logsRoot == null ? Paths.get(".") : logsRoot;
    }

    public Path resolveLogPath(String rawPath) {
        Path provided = Paths.get(rawPath == null ? "" : rawPath).normalize();
        if (provided.isAbsolute()) {
            return provided;
        }
        return logsRoot.resolve(provided).normalize();
    }

    public XLog loadLog(File file) throws Exception {
        if (!file.exists()) {
            throw new IllegalArgumentException("log not found: " + file.getAbsolutePath());
        }

        XesXmlParser parser = new XesXmlParser();
        List<XLog> logs = parser.parse(file);
        if (logs == null || logs.isEmpty()) {
            throw new IllegalStateException("XES parser returned empty log list");
        }
        return logs.get(0);
    }
}