package com.minersweeper.javaservice.app.logging;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class UnknownExtensionLogFilterTest {

    @Test
    public void suppressesLifecycleTraceRowsFromCurrentIncidentLog() {
        assertTrue(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[Accepted+In Progress,Accepted+In Progress,Queued+Awaiting Assignment,Accepted+Wait - User,Accepted+Wait - User] -1.0"
        ));
        assertTrue(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[Accepted+In Progress] 1.0"
        ));
    }

    @Test
    public void suppressesOtherLifecycleTraceRowsWithSameStructure() {
        assertTrue(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[Started+On Hold,Reopened+Needs Review,Closed+Resolved] 0.25"
        ));
    }

    @Test
    public void keepsEvaluationAndErrorLinesVisible() {
        assertFalse(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[EVAL] evaluation_summary status=ok metrics=[fitness,precision]"
        ));
        assertFalse(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "prom_service error [pipeline_failed]: ConcurrentModificationException"
        ));
    }

    @Test
    public void doesNotSuppressBracketedMessagesWithoutLifecycleShape() {
        assertFalse(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[case=4711, activity=Approve] -1.0"
        ));
        assertFalse(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[Accepted In Progress,Completed Resolved] -1.0"
        ));
    }

    @Test
    public void suppressesExplicitToolboxNoise() {
        assertTrue(UnknownExtensionLogFilter.shouldSuppressPromNoiseLine(
            "[Toolbox] Sorting on text values."
        ));
    }
}
