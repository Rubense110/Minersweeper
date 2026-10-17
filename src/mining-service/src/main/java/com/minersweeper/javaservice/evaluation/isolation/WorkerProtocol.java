package com.minersweeper.javaservice.evaluation.isolation;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.api.dto.EvaluationResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;

/** Private, file-based IPC. Plugin stdout/stderr never carries the protocol. */
public final class WorkerProtocol {
    public static final ObjectMapper JSON = new ObjectMapper();
    public static final class Command {
        public String operation = "evaluate";
        public PipelineRequest request;
        public String experiment;
    }
    public static final class Reply {
        public EvaluationResult result;
        public String code;
        public String message;
    }
    public static void publish(Path path, Object value) throws Exception {
        Path temporary = path.resolveSibling(path.getFileName()+".pending");
        JSON.writeValue(temporary.toFile(), value);
        Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }
    private WorkerProtocol() {}
}
