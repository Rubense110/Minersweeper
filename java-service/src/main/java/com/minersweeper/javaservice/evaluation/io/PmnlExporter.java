package com.minersweeper.javaservice.evaluation.io;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.plugins.pnml.exporting.PnmlExportNetToPNML;

public class PmnlExporter {

    public String exportPnml(PluginContext context, Petrinet net) throws Exception {
        File tmp = Files.createTempFile("pipeline-", ".pnml").toFile();
        try {
            new PnmlExportNetToPNML().exportPetriNetToPNMLFile(context, net, tmp);
            return new String(Files.readAllBytes(tmp.toPath()), StandardCharsets.UTF_8);
        } finally {
            Files.deleteIfExists(tmp.toPath()); // launches exception if failure happens
            //tmp.delete();  // Does not launch any exception. We are blind if using it
        }
    }
}
