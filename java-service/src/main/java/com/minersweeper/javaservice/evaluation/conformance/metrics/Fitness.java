package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import java.util.Map;
import org.processmining.plugins.petrinet.replayresult.PNRepResult;

public class Fitness implements ConformanceMetric {
    public static final String KEY = "fitness";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) throws Exception {
        Map<String, Object> info = computation.getReplayResult().getInfo();
        return MetricUtils.toDouble(info.get(PNRepResult.TRACEFITNESS), 0.0);
    }
}
