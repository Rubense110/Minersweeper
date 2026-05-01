import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import com.minersweeper.javaservice.artifacts.ArtifactStore;
import com.minersweeper.javaservice.evaluation.ExperimentCancelledException;
import com.minersweeper.javaservice.evaluation.ExperimentExecutionRegistry;
import com.minersweeper.javaservice.evaluation.PromPipelineEvaluator;
import java.lang.reflect.Method;
import java.nio.channels.ClosedByInterruptException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.Test;

public class PromPipelineEvaluatorCancellationTest {

    @Test
    public void normalizeCancellationFailureMapsInterruptedErrorsToCancelled() throws Exception {
        Path tmp = Files.createTempDirectory("prom-cancel-test");
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        PromPipelineEvaluator evaluator = new PromPipelineEvaluator(new ArtifactStore(tmp.toString()), tmp, registry);
        Method method = PromPipelineEvaluator.class.getDeclaredMethod(
            "normalizeCancellationFailure",
            String.class,
            Exception.class
        );
        method.setAccessible(true);

        registry.requestCancel("run_cancelled");
        Thread.currentThread().interrupt();

        Exception normalized = (Exception) method.invoke(
            evaluator,
            "run_cancelled",
            new ClosedByInterruptException()
        );

        assertTrue(normalized instanceof ExperimentCancelledException);
        assertFalse(Thread.currentThread().isInterrupted());
    }

    @Test
    public void normalizeCancellationFailurePreservesRegularErrors() throws Exception {
        Path tmp = Files.createTempDirectory("prom-cancel-pass-through-test");
        ExperimentExecutionRegistry registry = new ExperimentExecutionRegistry();
        PromPipelineEvaluator evaluator = new PromPipelineEvaluator(new ArtifactStore(tmp.toString()), tmp, registry);
        Method method = PromPipelineEvaluator.class.getDeclaredMethod(
            "normalizeCancellationFailure",
            String.class,
            Exception.class
        );
        method.setAccessible(true);

        IllegalStateException error = new IllegalStateException("boom");
        Exception normalized = (Exception) method.invoke(evaluator, "run_regular", error);

        assertSame(error, normalized);
        assertFalse(Thread.currentThread().isInterrupted());
    }
}
