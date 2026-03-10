import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.preprocessing.PreprocessingPipeline;
import java.util.LinkedHashMap;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;
import org.junit.Assert;
import org.junit.Test;

public class PreprocessingPipelineTest {
    @Test
    public void variantFilterRejectsEmptyResult() throws Exception {
        Path dir = Files.createTempDirectory("preprocessing-pipeline-test");
        try {
            Path logFile = TestFixtures.createTinyLog(dir, "tiny.xes");
            XLog log = new XesXmlParser().parse(logFile.toFile()).get(0);

            PipelineRequest request = new PipelineRequest();
            request.pipeline = new PipelineRequest.PipelineConfig();
            request.pipeline.preprocessing = new PipelineRequest.PreprocessingConfig();
            request.pipeline.preprocessing.key = "variant_filter";
            request.pipeline.preprocessing.method = "Variant Log Filter";
            request.pipeline.preprocessing.variant = "Variant Log Filter";
            request.pipeline.preprocessing.parameters = new LinkedHashMap<String, Object>();
            request.pipeline.preprocessing.parameters.put("keep_threshold_vf", Integer.valueOf(0));
            request.pipeline.preprocessings = Collections.singletonList(request.pipeline.preprocessing);

            try {
                new PreprocessingPipeline().apply(null, log, request);
                Assert.fail("Expected preprocessing to reject empty logs");
            } catch (IllegalArgumentException error) {
                Assert.assertTrue(error.getMessage().contains("preprocessing produced empty log"));
            }
        } finally {
            Files.deleteIfExists(dir.resolve("tiny.xes"));
            Files.deleteIfExists(dir);
        }
    }
}
