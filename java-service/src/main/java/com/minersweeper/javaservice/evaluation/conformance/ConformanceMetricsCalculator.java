package com.minersweeper.javaservice.evaluation.conformance;

import com.minersweeper.javaservice.evaluation.conformance.metrics.ConformanceMetric;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.deckfour.xes.model.XLog;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.semantics.petrinet.Marking;

public class ConformanceMetricsCalculator {
    private final Map<String, ConformanceMetric> metricsByKey;

    public ConformanceMetricsCalculator() {
        this.metricsByKey = new LinkedHashMap<String, ConformanceMetric>(ConformanceMetricCatalog.metricsByKey());
    }

    public Map<String, Double> compute(
        PluginContext context,
        XLog log,
        Petrinet net,
        Marking initial,
        Marking fin,
        Iterable<String> requestedMetrics
    ) throws Exception {
        if (requestedMetrics == null) {
            throw new IllegalArgumentException("requested metrics cannot be null");
        }

        Set<String> canonicalRequestedMetrics = new LinkedHashSet<String>();
        for (String requestedMetric : requestedMetrics) {
            if (!metricsByKey.containsKey(requestedMetric)) {
                throw new IllegalArgumentException("unsupported metric: " + requestedMetric);
            }
            canonicalRequestedMetrics.add(requestedMetric);
        }

        ConformanceComputation computation = new ConformanceComputation(context, log, net, initial, fin);

        Map<String, Double> metrics = new LinkedHashMap<String, Double>();
        for (String metricKey : canonicalRequestedMetrics) {
            ConformanceMetric metric = metricsByKey.get(metricKey);
            metrics.put(metricKey, MetricUtils.clamp01(metric.compute(computation)));
        }
        return metrics;
    }
}
