package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.utils.MetricUtils;
import java.util.Map;
import org.processmining.plugins.petrinet.replayresult.PNRepResult;

public class Fitness {
    public static double compute(PNRepResult replayResult) {
        Map<String, Object> info = replayResult.getInfo();
        return MetricUtils.toDouble(info.get(PNRepResult.TRACEFITNESS), 0.0);
    }
}