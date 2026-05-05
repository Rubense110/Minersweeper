package com.minersweeper.javaservice.evaluation.preprocessing;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfo;
import org.deckfour.xes.info.impl.XLogInfoImpl;
import org.deckfour.xes.model.XLog;
import org.processmining.filterd.filters.FilterdEventRateFilter;
import org.processmining.filterd.parameters.Parameter;
import org.processmining.filterd.parameters.ParameterMultipleFromSet;
import org.processmining.filterd.parameters.ParameterOneFromSet;
import org.processmining.filterd.parameters.ParameterValueFromRange;
import org.processmining.filterd.tools.Toolbox;
import org.processmining.framework.plugin.PluginContext;
import org.processmining.logfiltering.algorithms.FilterBasedOnRelationMatrixK;
import org.processmining.logfiltering.parameters.MatrixFilterParameter;
import org.processmining.logfiltering.plugins.RepairLog;
import org.processmining.logfiltering.plugins.VariantCounterPlugin;

public final class PreprocessingPipeline {
    private static final Set<String> SUPPORTED_KEYS = Collections.unmodifiableSet(
        new HashSet<String>(
            Arrays.asList(
                "matrix_filter",
                "repair_log_filter",
                "variant_filter",
                "projection_filter"
            )
        )
    );

    public XLog apply(PluginContext context, XLog sourceLog, PipelineRequest request) throws Exception {
        if (sourceLog == null) {
            throw new IllegalArgumentException("source log is required for preprocessing");
        }
        List<PipelineRequest.PreprocessingConfig> preprocessings = steps(request);
        if (preprocessings.isEmpty()) {
            return sourceLog;
        }

        XLog current = sourceLog;
        for (PipelineRequest.PreprocessingConfig preprocessing : preprocessings) {
            String key = normalizeKey(preprocessing == null ? null : preprocessing.key);
            if ("projection_filter".equals(key)) {
                current = applyProjectionFilter(current, preprocessing);
            } else if ("variant_filter".equals(key)) {
                current = applyVariantFilter(current, preprocessing);
            } else if ("repair_log_filter".equals(key)) {
                current = applyRepairLogFilter(current, preprocessing);
            } else if ("matrix_filter".equals(key)) {
                current = applyMatrixFilter(context, current, preprocessing);
            } else {
                throw new IllegalArgumentException("unsupported preprocessing key: " + key);
            }
            current = requireNonEmptyLog(current, key);
        }
        return current;
    }

    public static Set<String> supportedKeys() {
        return SUPPORTED_KEYS;
    }

    public static List<PipelineRequest.PreprocessingConfig> steps(PipelineRequest request) {
        if (request == null || request.pipeline == null) {
            return Collections.emptyList();
        }
        if (request.pipeline.preprocessings != null && !request.pipeline.preprocessings.isEmpty()) {
            return request.pipeline.preprocessings;
        }
        if (request.pipeline.preprocessing != null) {
            return Collections.singletonList(request.pipeline.preprocessing);
        }
        return Collections.emptyList();
    }

    private static XLog applyProjectionFilter(XLog inputLog, PipelineRequest.PreprocessingConfig preprocessing) {
        int keepThreshold = clampInt(
            ParameterReader.intParam(preprocessing.parameters, "keep_threshold_p", 50),
            0,
            100
        );
        if (inputLog.isEmpty()) {
            return (XLog) inputLog.clone();
        }

        XLogInfo logInfo = XLogInfoImpl.create(inputLog, XLogInfoImpl.STANDARD_CLASSIFIER);
        XEventClasses eventClasses = logInfo.getEventClasses();
        if (eventClasses == null || eventClasses.getClasses().isEmpty()) {
            return (XLog) inputLog.clone();
        }

        List<String> allEventClasses = new ArrayList<String>();
        for (XEventClass eventClass : eventClasses.getClasses()) {
            allEventClasses.add(eventClass.toString());
        }

        ParameterOneFromSet rate = new ParameterOneFromSet(
            "rate",
            "Choose rate type",
            "Frequency",
            Arrays.asList("Frequency", "Occurrence")
        );
        ParameterValueFromRange<Integer> threshold = new ParameterValueFromRange<Integer>(
            "threshold",
            "Select threshold",
            Integer.valueOf(keepThreshold),
            Arrays.asList(Integer.valueOf(0), Integer.valueOf(100)),
            Integer.TYPE
        );
        ParameterOneFromSet selectionType = new ParameterOneFromSet(
            "selectionType",
            "Selection type",
            "Filter in",
            Arrays.asList("Filter in", "Filter out")
        );
        List<String> desiredEventClasses = Toolbox.computeDesiredEventsFromThreshold(threshold, rate, eventClasses);
        ParameterMultipleFromSet desiredEvents = new ParameterMultipleFromSet(
            "desiredEvents",
            "Selected classes according to threshold",
            allEventClasses,
            desiredEventClasses
        );

        List<Parameter> parameters = new ArrayList<Parameter>();
        parameters.add(rate);
        parameters.add(threshold);
        parameters.add(selectionType);
        parameters.add(desiredEvents);
        return new FilterdEventRateFilter().filter(inputLog, parameters);
    }

    private static XLog applyVariantFilter(XLog sourceLog, PipelineRequest.PreprocessingConfig preprocessing) {
        int keepThreshold = clampInt(
            ParameterReader.intParam(preprocessing.parameters, "keep_threshold_vf", 50),
            0,
            100
        );
        XLog workingLog = ensureClassifier(sourceLog);
        if (workingLog.isEmpty()) {
            return (XLog) workingLog.clone();
        }
        MatrixFilterParameter parameters = new MatrixFilterParameter(
            keepThreshold,
            XLogInfoImpl.NAME_CLASSIFIER
        );
        XLog filteredLog = VariantCounterPlugin.run(null, workingLog, parameters);
        return restoreClassifiers(filteredLog, workingLog);
    }

    private static XLog applyMatrixFilter(
        PluginContext context,
        XLog sourceLog,
        PipelineRequest.PreprocessingConfig preprocessing
    ) {
        if (sourceLog.isEmpty()) {
            return (XLog) sourceLog.clone();
        }
        int subsequenceLength = clampInt(
            ParameterReader.intParam(preprocessing.parameters, "subsequence_length_mf", 2),
            1,
            Integer.MAX_VALUE
        );
        double probabilityOfRemoval = clampDouble(
            ParameterReader.doubleParam(preprocessing.parameters, "probability_of_removal_mf", 0.15d),
            0.0d,
            1.0d
        );
        XLog workingLog = ensureClassifier(sourceLog);
        MatrixFilterParameter parameters = new MatrixFilterParameter();
        parameters.setProbabilityOfRemoval(probabilityOfRemoval);
        parameters.setSubsequenceLength(subsequenceLength);
        XLog filteredLog = FilterBasedOnRelationMatrixK.apply(workingLog, parameters);
        return restoreClassifiers(filteredLog, workingLog);
    }

    private static XLog applyRepairLogFilter(XLog sourceLog, PipelineRequest.PreprocessingConfig preprocessing) {
        XLog workingLog = ensureClassifier(sourceLog);
        if (workingLog.isEmpty()) {
            return (XLog) workingLog.clone();
        }
        int windowSize = clampInt(
            ParameterReader.intParam(preprocessing.parameters, "subsequence_length_rl", 2),
            1,
            Integer.MAX_VALUE
        );
        double probabilityOfRemoval = clampDouble(
            ParameterReader.doubleParam(preprocessing.parameters, "probability_of_removal_rl", 0.15d),
            0.0d,
            1.0d
        );
        MatrixFilterParameter parameters = new MatrixFilterParameter();
        parameters.setProbabilityOfRemoval(probabilityOfRemoval);
        parameters.setSubsequenceLength(windowSize);
        XLog filteredLog = RepairLog.run(null, workingLog, parameters);
        return restoreClassifiers(filteredLog, workingLog);
    }

    private static XLog ensureClassifier(XLog sourceLog) {
        if (sourceLog.getClassifiers() != null && !sourceLog.getClassifiers().isEmpty()) {
            return sourceLog;
        }
        XLog cloned = (XLog) sourceLog.clone();
        cloned.getClassifiers().add(new XEventNameClassifier());
        return cloned;
    }

    private static XLog restoreClassifiers(XLog filteredLog, XLog sourceLog) {
        if (filteredLog == null) {
            return null;
        }
        for (XEventClassifier classifier : sourceLog.getClassifiers()) {
            if (!filteredLog.getClassifiers().contains(classifier)) {
                filteredLog.getClassifiers().add(classifier);
            }
        }
        return filteredLog;
    }

    private static XLog requireNonEmptyLog(XLog log, String preprocessingKey) {
        if (log == null) {
            throw new IllegalArgumentException("preprocessing returned null log: " + preprocessingKey);
        }
        if (log.isEmpty()) {
            throw new IllegalArgumentException("preprocessing produced empty log: " + preprocessingKey);
        }
        return log;
    }

    private static String normalizeKey(String key) {
        return TextUtils.safe(key).toLowerCase(Locale.ROOT);
    }

    private static int clampInt(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static double clampDouble(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
