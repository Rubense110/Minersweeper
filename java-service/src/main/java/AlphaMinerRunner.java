import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;
import org.processmining.alphaminer.parameters.AlphaMinerParameters;
import org.processmining.alphaminer.parameters.AlphaRobustMinerParameters;
import org.processmining.alphaminer.parameters.AlphaVersion;
import org.processmining.alphaminer.plugins.AlphaMinerPlugin;
import org.processmining.contexts.cli.CLIContext;
import org.processmining.contexts.cli.CLIPluginContext;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.plugins.pnml.exporting.PnmlExportNetToPNML;

public class AlphaMinerRunner {

    public static String run(Path logsRoot, String logPath, String variant) throws Exception {
        Path logFile = logsRoot.resolve(logPath).normalize();
        if (!Files.exists(logFile)) {
            throw new IllegalArgumentException("log not found: " + logFile);
        }

        XLog log = loadLog(logFile.toFile());
        PluginContext context = createContext();
        XEventClassifier classifier = new XEventNameClassifier();
        AlphaVersion version = resolveVariant(variant);
        Object[] result;
        if (AlphaVersion.ROBUST.equals(version)) {
            // Same issue as in PromPipelineEvaluator: this ProM version requires robust-specific params.
            AlphaRobustMinerParameters robustParams = new AlphaRobustMinerParameters(AlphaVersion.ROBUST);
            result = AlphaMinerPlugin.apply(context, log, classifier, robustParams);
        } else {
            AlphaMinerParameters params = new AlphaMinerParameters(version);
            result = AlphaMinerPlugin.apply(context, log, classifier, params);
        }
        if (result == null || result.length == 0 || !(result[0] instanceof Petrinet)) {
            throw new IllegalStateException("AlphaMiner did not return a Petri net");
        }

        Petrinet net = (Petrinet) result[0];
        File tmp = Files.createTempFile("alpha-", ".pnml").toFile();
        new PnmlExportNetToPNML().exportPetriNetToPNMLFile(context, net, tmp);

        byte[] bytes = Files.readAllBytes(tmp.toPath());
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static XLog loadLog(File file) throws Exception {
        XesXmlParser parser = new XesXmlParser();
        List<XLog> logs = parser.parse(file);
        if (logs == null || logs.isEmpty()) {
            throw new IllegalStateException("XES parser returned empty log list");
        }
        return logs.get(0);
    }

    private static PluginContext createContext() {
        CLIContext global = new CLIContext();
        return new CLIPluginContext(global, "minersweeper");
    }

    private static AlphaVersion resolveVariant(String variant) {
        if (variant == null || variant.trim().isEmpty()) {
            return AlphaVersion.CLASSIC;
        }
        String key = variant.trim().toUpperCase().replace("-", "_");
        return AlphaVersion.valueOf(key);
    }
}
