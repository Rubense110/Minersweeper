package com.minersweeper.javaservice.evaluation.discovery;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;

public interface MinerDiscoverer {
    String key();

    DiscoveryArtifact discover(PluginContext context, XLog log, PipelineRequest request) throws Exception;
}
