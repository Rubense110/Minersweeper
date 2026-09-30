package com.minersweeper.javaservice.evaluation.io;

import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.plugins.pnml.exporting.PnmlExportNetToPNML;
import org.processmining.plugins.pnml.base.Pnml;

public class PmnlExporter {
    public String exportPnml(PluginContext context, Petrinet net) throws Exception {
        // ProM already exposes the same conversion without the temporary file.
        return new PnmlExportNetToPNML().exportPetriNetToPNMLOrEPNMLString(context, net, Pnml.PnmlType.PNML, true)
            .replace("encoding=\"ISO-8859-1\"", "encoding=\"UTF-8\"");
    }
}
