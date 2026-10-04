package com.minersweeper.javaservice.evaluation.reproducibility;

import com.minersweeper.javaservice.evaluation.ReproducibilityException;
import java.net.URL;
import processmining.splitminer.SplitMiner;
import processmining.splitminer.oracle.Oracle;
import processmining.splitminer.oracle.OracleItem;
import bpmn.helper.GatewayMap;
import processmining.splitminer.dfgp.DirectlyFollowGraphPlus;

/** Rejects classpaths which silently load part or all of the original Split fork. */
public final class SplitMinerProvenance {
    public static final String VERSION = "minersweeper-split-v2";
    private static volatile boolean verified;
    private SplitMinerProvenance() {}

    public static void verify() {
        if (verified) return;
        synchronized (SplitMinerProvenance.class) {
            if (verified) return;
            try {
                URL service = origin(SplitMinerProvenance.class);
                if (!VERSION.equals(SplitMiner.determinismPolicyVersion())) fail();
                if (!VERSION.equals(DirectlyFollowGraphPlus.determinismPolicyVersion())) fail();
                for (Class<?> type : new Class<?>[]{SplitMiner.class, Oracle.class,
                        OracleItem.class, GatewayMap.class, DirectlyFollowGraphPlus.class})
                    if (!service.equals(origin(type))) fail();
            } catch (LinkageError | SecurityException error) {
                fail();
            }
            verified = true;
        }
    }

    private static URL origin(Class<?> type) {
        if (type.getProtectionDomain().getCodeSource() == null) {
            fail();
        }
        return type.getProtectionDomain().getCodeSource().getLocation();
    }

    private static void fail() {
        throw new ReproducibilityException("REPRODUCIBILITY_SPLIT_CLASSPATH_MISMATCH");
    }
}
