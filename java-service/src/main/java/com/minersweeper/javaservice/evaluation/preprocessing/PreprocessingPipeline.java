package com.minersweeper.javaservice.evaluation.preprocessing;

import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.utils.ParameterReader;
import com.minersweeper.javaservice.evaluation.utils.TextUtils;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.deckfour.xes.classification.XEventClass;
import org.deckfour.xes.classification.XEventClasses;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.info.XLogInfo;
import org.deckfour.xes.info.impl.XLogInfoImpl;
import org.deckfour.xes.model.XEvent;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.model.XTrace;
import org.processmining.causalactivitymatrix.algorithms.FilterLogUsingMatrixAlgorithm;
import org.processmining.causalactivitymatrix.filters.CausalityBasedFilter;
import org.processmining.causalactivitymatrix.filters.CausalityBasedFilterManager;
import org.processmining.causalactivitymatrix.models.CausalActivityMatrix;
import org.processmining.causalactivitymatrix.parameters.FilterLogUsingMatrixParameters;
import org.processmining.causalactivitymatrixminer.algorithms.DiscoverFromEventLogAlgorithm;
import org.processmining.causalactivitymatrixminer.miners.MatrixMiner;
import org.processmining.causalactivitymatrixminer.miners.MatrixMinerManager;
import org.processmining.causalactivitymatrixminer.parameters.DiscoverFromEventLogParameters;
import org.processmining.filterd.filters.FilterdEventRateFilter;
import org.processmining.filterd.filters.FilterdTraceFrequencyFilter;
import org.processmining.filterd.parameters.Parameter;
import org.processmining.filterd.parameters.ParameterMultipleFromSet;
import org.processmining.filterd.parameters.ParameterOneFromSet;
import org.processmining.filterd.parameters.ParameterRangeFromRange;
import org.processmining.filterd.parameters.ParameterValueFromRange;
import org.processmining.filterd.tools.Toolbox;
import org.processmining.framework.plugin.PluginContext;

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

        List<XEventClassifier> classifiers = Toolbox.computeAllClassifiers(workingLog);
        if (classifiers.isEmpty()) {
            workingLog.getClassifiers().add(new XEventNameClassifier());
            classifiers = Toolbox.computeAllClassifiers(workingLog);
        }
        XEventClassifier selectedClassifier = classifiers.get(0);

        Map<XTrace, List<Integer>> variantsToTraceIndices = Toolbox.getVariantsToTraceIndices(workingLog, selectedClassifier);
        int minOccurrence = Integer.MAX_VALUE;
        int maxOccurrence = Integer.MIN_VALUE;
        for (List<Integer> traceIndices : variantsToTraceIndices.values()) {
            int size = traceIndices.size();
            if (size < minOccurrence) {
                minOccurrence = size;
            }
            if (size > maxOccurrence) {
                maxOccurrence = size;
            }
        }
        if (minOccurrence == Integer.MAX_VALUE) {
            minOccurrence = 0;
        }
        if (maxOccurrence == Integer.MIN_VALUE) {
            maxOccurrence = workingLog.size();
        }

        ParameterOneFromSet classifier = new ParameterOneFromSet(
            "classifier",
            "Select classifier",
            selectedClassifier.toString(),
            Arrays.asList(selectedClassifier.toString())
        );
        ParameterOneFromSet thresholdType = new ParameterOneFromSet(
            "FreqOcc",
            "Threshold type",
            "frequency",
            Arrays.asList("frequency", "occurrence")
        );

        double lowerPercent = (double) clampInt(100 - keepThreshold, 0, 100);
        List<Double> frequencyRange = Arrays.asList(Double.valueOf(lowerPercent), Double.valueOf(100.0d));
        ParameterRangeFromRange<Double> rangeFreq = new ParameterRangeFromRange<Double>(
            "rangeFreq",
            "Threshold",
            frequencyRange,
            frequencyRange,
            Double.TYPE
        );
        List<Integer> occurrenceRange = Arrays.asList(Integer.valueOf(minOccurrence), Integer.valueOf(maxOccurrence));
        ParameterRangeFromRange<Integer> rangeOcc = new ParameterRangeFromRange<Integer>(
            "rangeOcc",
            "Threshold",
            occurrenceRange,
            occurrenceRange,
            Integer.TYPE
        );
        ParameterOneFromSet filterInOut = new ParameterOneFromSet(
            "filterInOut",
            "Filter mode",
            "in",
            Arrays.asList("in", "out")
        );

        List<Parameter> parameters = new ArrayList<Parameter>();
        parameters.add(classifier);
        parameters.add(thresholdType);
        parameters.add(rangeFreq);
        parameters.add(rangeOcc);
        parameters.add(filterInOut);
        return new FilterdTraceFrequencyFilter().filter(workingLog, parameters);
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
            3
        );
        double probabilityOfRemoval = clampDouble(
            ParameterReader.doubleParam(preprocessing.parameters, "probability_of_removal_mf", 0.15d),
            0.0d,
            1.0d
        );

        DiscoverFromEventLogParameters discoveryParams = new DiscoverFromEventLogParameters(sourceLog);
        discoveryParams.setShowClassifierPanel(false);
        discoveryParams.setAutoAdjust(true);
        discoveryParams.setTryConnections(false);
        discoveryParams.setClassifier(XLogInfoImpl.STANDARD_CLASSIFIER);
        discoveryParams.setMiner(resolveMatrixMinerName(subsequenceLength));

        CausalActivityMatrix matrix = new DiscoverFromEventLogAlgorithm().apply(context, sourceLog, discoveryParams);

        FilterLogUsingMatrixParameters filterParams = new FilterLogUsingMatrixParameters(sourceLog);
        filterParams.setClassifier(discoveryParams.getClassifier());
        filterParams.setTryConnections(false);
        filterParams.setAbsolute(false);
        filterParams.setRelativeThreshold(clampInt((int) Math.round(probabilityOfRemoval * 100.0d), 0, 100));
        filterParams.setFilter(resolveMatrixFilterName(subsequenceLength));

        return new FilterLogUsingMatrixAlgorithm().apply(context, sourceLog, matrix, filterParams);
    }

    private static XLog applyRepairLogFilter(XLog sourceLog, PipelineRequest.PreprocessingConfig preprocessing) {
        if (sourceLog.isEmpty()) {
            return (XLog) sourceLog.clone();
        }
        int windowSize = clampInt(
            ParameterReader.intParam(preprocessing.parameters, "subsequence_length_rl", 2),
            1,
            5
        );
        double probabilityOfRemoval = clampDouble(
            ParameterReader.doubleParam(preprocessing.parameters, "probability_of_removal_rl", 0.15d),
            0.0d,
            1.0d
        );

        // Approximation of window-based repair: identify infrequent windows and remove
        // representative events from those windows with deterministic probability.
        XEventClassifier classifier = XLogInfoImpl.STANDARD_CLASSIFIER;
        Map<String, Integer> windowCounts = new HashMap<String, Integer>();
        for (XTrace trace : sourceLog) {
            List<String> identities = eventIdentities(trace, classifier);
            if (identities.size() < windowSize) {
                continue;
            }
            for (int i = 0; i <= identities.size() - windowSize; i++) {
                String key = windowKey(identities, i, windowSize);
                Integer count = windowCounts.get(key);
                windowCounts.put(key, Integer.valueOf(count == null ? 1 : count.intValue() + 1));
            }
        }
        if (windowCounts.isEmpty()) {
            return (XLog) sourceLog.clone();
        }

        List<Integer> counts = new ArrayList<Integer>(windowCounts.values());
        Collections.sort(counts);
        int quantileIndex = clampInt((int) Math.floor((counts.size() - 1) * probabilityOfRemoval), 0, counts.size() - 1);
        int rareWindowThreshold = counts.get(quantileIndex).intValue();

        XLog repairedLog = Toolbox.initializeLog(sourceLog);
        for (int traceIndex = 0; traceIndex < sourceLog.size(); traceIndex++) {
            XTrace trace = sourceLog.get(traceIndex);
            List<String> identities = eventIdentities(trace, classifier);
            Set<Integer> indexesToRemove = new HashSet<Integer>();
            if (identities.size() >= windowSize) {
                for (int i = 0; i <= identities.size() - windowSize; i++) {
                    String key = windowKey(identities, i, windowSize);
                    Integer occurrences = windowCounts.get(key);
                    if (occurrences == null || occurrences.intValue() > rareWindowThreshold) {
                        continue;
                    }
                    int center = i + (windowSize / 2);
                    if (shouldRemove(traceIndex, center, key, probabilityOfRemoval)) {
                        indexesToRemove.add(Integer.valueOf(center));
                    }
                }
            }

            XTrace repairedTrace = org.deckfour.xes.factory.XFactoryRegistry.instance()
                .currentDefault()
                .createTrace(trace.getAttributes());
            for (int eventIndex = 0; eventIndex < trace.size(); eventIndex++) {
                if (!indexesToRemove.contains(Integer.valueOf(eventIndex))) {
                    repairedTrace.add(trace.get(eventIndex));
                }
            }
            if (repairedTrace.isEmpty() && !trace.isEmpty()) {
                repairedTrace.add(trace.get(0));
            }
            if (!repairedTrace.isEmpty()) {
                repairedLog.add(repairedTrace);
            }
        }
        return repairedLog;
    }

    private static boolean shouldRemove(int traceIndex, int eventIndex, String key, double probability) {
        if (probability <= 0.0d) {
            return false;
        }
        if (probability >= 1.0d) {
            return true;
        }
        int hash = (traceIndex + 31) * 17 + eventIndex * 31 + key.hashCode();
        int positive = hash & Integer.MAX_VALUE;
        double sample = ((double) positive) / ((double) Integer.MAX_VALUE);
        return sample < probability;
    }

    private static List<String> eventIdentities(XTrace trace, XEventClassifier classifier) {
        List<String> identities = new ArrayList<String>();
        for (XEvent event : trace) {
            String identity;
            try {
                identity = classifier.getClassIdentity(event);
            } catch (Exception ignored) {
                identity = TextUtils.safeObj(event.getAttributes().get("concept:name"));
            }
            identities.add(TextUtils.safe(identity));
        }
        return identities;
    }

    private static String windowKey(List<String> identities, int start, int length) {
        StringBuilder out = new StringBuilder(length * 8);
        for (int i = 0; i < length; i++) {
            if (i > 0) {
                out.append('\u001F');
            }
            out.append(identities.get(start + i));
        }
        return out.toString();
    }

    private static String resolveMatrixMinerName(int subsequenceLength) {
        String fallback = MatrixMinerManager.getInstance().getMiner(null).getName();
        List<MatrixMiner> miners = MatrixMinerManager.getInstance().getMiners();
        String preferred;
        if (subsequenceLength <= 1) {
            preferred = "Directly Follows";
        } else if (subsequenceLength >= 3) {
            preferred = "Heuristics";
        } else {
            preferred = fallback;
        }
        for (MatrixMiner miner : miners) {
            if (preferred.equals(miner.getName())) {
                return miner.getName();
            }
        }
        return fallback;
    }

    private static String resolveMatrixFilterName(int subsequenceLength) {
        String preferred;
        if (subsequenceLength <= 1) {
            preferred = "Minimal Causality";
        } else if (subsequenceLength >= 3) {
            preferred = "Context Average Causality";
        } else {
            preferred = "Average Causality";
        }
        List<CausalityBasedFilter> filters = CausalityBasedFilterManager.getInstance().getFilters();
        for (CausalityBasedFilter filter : filters) {
            if (preferred.equals(filter.getName())) {
                return filter.getName();
            }
        }
        return CausalityBasedFilterManager.getInstance().getFilter(null).getName();
    }

    private static XLog ensureClassifier(XLog sourceLog) {
        if (sourceLog.getClassifiers() != null && !sourceLog.getClassifiers().isEmpty()) {
            return sourceLog;
        }
        XLog cloned = (XLog) sourceLog.clone();
        cloned.getClassifiers().add(new XEventNameClassifier());
        return cloned;
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
