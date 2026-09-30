#!/usr/bin/env python3
"""Compare preprocessing alone on identical complete XES inputs and two service jars.

Uses the production Java 8 runtime; no mining or approximate input sampling.
Reports elapsed time, JVM allocations and trace/event/attribute equivalence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[5]
LOGS = {
    "financial": "BPI_Challenge_2012.xes",
    "incidents": "BPI_Challenge_2013_incidents.xes",
    "hospital": "Hospital Billing - Event Log.xes",
    "sepsis": "Sepsis Cases - Event Log.xes",
}
JAVA = r'''
import com.minersweeper.javaservice.api.dto.PipelineRequest;
import com.minersweeper.javaservice.evaluation.preprocessing.PreprocessingPipeline;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.management.ManagementFactory;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.io.File;
import java.util.*;
import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.*;

public class PreprocessingBenchmark {
    static void add(MessageDigest digest, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        digest.update(java.nio.ByteBuffer.allocate(4).putInt(bytes.length).array()); digest.update(bytes);
    }
    static void attributes(MessageDigest digest, XAttributeMap attributes) {
        for (String key : new TreeSet<String>(attributes.keySet())) {
            XAttribute value = attributes.get(key);
            add(digest, key); add(digest, value.getClass().getName());
            add(digest, value.toString());
            if (value.hasAttributes()) attributes(digest, value.getAttributes());
            if (value instanceof XAttributeCollection) for (XAttribute child : ((XAttributeCollection) value).getCollection()) {
                add(digest, child.getKey()); add(digest, child.toString());
                if (child.hasAttributes()) attributes(digest, child.getAttributes());
            }
        }
        add(digest, "END_ATTRIBUTES");
    }
    static String digest(XLog log) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        attributes(digest, log.getAttributes());
        for (XTrace trace : log) {
            add(digest, "TRACE"); attributes(digest, trace.getAttributes());
            for (XEvent event : trace) { add(digest, "EVENT"); attributes(digest, event.getAttributes()); }
        }
        StringBuilder result = new StringBuilder();
        for (byte value : digest.digest()) result.append(String.format("%02x", value & 255));
        return result.toString();
    }
    static long allocated() {
        com.sun.management.ThreadMXBean bean = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        if (!bean.isThreadAllocatedMemorySupported()) throw new IllegalStateException("allocation measurements unavailable");
        if (!bean.isThreadAllocatedMemoryEnabled()) bean.setThreadAllocatedMemoryEnabled(true);
        return bean.getThreadAllocatedBytes(Thread.currentThread().getId());
    }
    static PipelineRequest request(String key, Object... parameters) {
        PipelineRequest request = new PipelineRequest(); request.experiment_id = "benchmark";
        request.pipeline = new PipelineRequest.PipelineConfig();
        request.pipeline.preprocessing = new PipelineRequest.PreprocessingConfig();
        request.pipeline.preprocessing.key = key;
        request.pipeline.preprocessing.parameters = new LinkedHashMap<String,Object>();
        for (int i = 0; i < parameters.length; i += 2) request.pipeline.preprocessing.parameters.put((String) parameters[i], parameters[i+1]);
        request.pipeline.miner = new PipelineRequest.MinerConfig();
        return request;
    }
    public static void main(String[] args) throws Exception {
        XLog source = new XesXmlParser().parse(new File(args[0])).get(0);
        String original = digest(source);
        PreprocessingPipeline pipeline = new PreprocessingPipeline();
        PipelineRequest[] cases = new PipelineRequest[]{
            request("variant_filter", "keep_threshold_vf", 80),
            request("projection_filter", "keep_threshold_p", 75),
            request("matrix_filter", "subsequence_length_mf", 2, "probability_of_removal_mf", .15d),
            request("repair_log_filter", "subsequence_length_rl", 2, "probability_of_removal_rl", .15d)
        };
        ObjectMapper mapper = new ObjectMapper();
        for (PipelineRequest request : cases) for (int pass = 0; pass < 3; pass++) {
            request.pipeline.miner.key = "miner" + pass; // intentionally irrelevant to preprocessing reuse
            long bytesBefore = allocated(), start = System.nanoTime();
            XLog output = pipeline.apply(null, source, request);
            long nanos = System.nanoTime() - start, bytes = allocated() - bytesBefore;
            int events = 0; for (XTrace trace : output) events += trace.size();
            Map<String,Object> row = new LinkedHashMap<String,Object>();
            row.put("filter", request.pipeline.preprocessing.key); row.put("pass", pass);
            row.put("seconds", nanos / 1e9); row.put("allocated_bytes", bytes);
            row.put("traces", output.size()); row.put("events", events); row.put("digest", digest(output));
            row.put("global_trace_attributes", output.getGlobalTraceAttributes().size());
            row.put("global_event_attributes", output.getGlobalEventAttributes().size());
            System.out.println("BENCH_JSON " + mapper.writeValueAsString(row));
        }
        if (!original.equals(digest(source))) throw new AssertionError("source log mutated");
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-jar", required=True, type=Path)
    parser.add_argument("--after-jar", type=Path, default=ROOT / "src/mining-service/target/prom-service-0.1.0.jar")
    parser.add_argument("--logs", nargs="+", choices=list(LOGS), default=list(LOGS))
    parser.add_argument("--java-home", type=Path, default=Path("/usr/lib/jvm/java-8-openjdk-amd64"))
    parser.add_argument("--heap-gb", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    prom = ROOT / "tools/prom-lite-1.4-all-platforms"
    jars = sorted(str(path) for folder in ("lib", "packages") for path in (prom / folder).rglob("*.jar") if path.name != "split-miner-1.7.1-all.jar")
    dependencies = str(ROOT / "src/mining-service/target/dependency/*")
    results = {}
    with tempfile.TemporaryDirectory(prefix="ms-preprocessing-") as temporary:
        probe = Path(temporary) / "PreprocessingBenchmark.java"
        probe.write_text(JAVA)
        subprocess.run([str(args.java_home / "bin/javac"), "-cp", ":".join([str(args.after_jar), dependencies, *jars]), str(probe)], check=True)
        for log_name in args.logs:
            results[log_name] = {}
            for revision, jar in (("before", args.before_jar), ("after", args.after_jar)):
                cp = ":".join([temporary, str(jar), dependencies, *jars])
                command = [str(args.java_home / "bin/java"), "-Xms256m", f"-Xmx{args.heap_gb}g", "-XX:+UseG1GC", "-XX:ActiveProcessorCount=4", "-Djava.awt.headless=true", "-cp", cp, "PreprocessingBenchmark", str(ROOT / "event_logs" / LOGS[log_name])]
                start = time.monotonic()
                run = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600, env={**os.environ, "PROM_PREPROCESS_CACHE_MB": "256"})
                (args.output / f"{revision}-{log_name}.log").write_text(run.stdout)
                if run.returncode:
                    raise RuntimeError(f"{revision}-{log_name} failed: {run.returncode}; see output log")
                rows = [json.loads(line[len("BENCH_JSON "):]) for line in run.stdout.splitlines() if line.startswith("BENCH_JSON ")]
                if len(rows) != 12:
                    raise AssertionError(f"Expected 12 filter runs, got {len(rows)}")
                results[log_name][revision] = {"jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "process_seconds": time.monotonic() - start, "measurements": rows}
                (args.output / "results.json").write_text(json.dumps(results, indent=2))
                print(json.dumps({"log": log_name, "revision": revision, "filter_seconds": sum(row['seconds'] for row in rows)}), flush=True)
            for before, after in zip(results[log_name]["before"]["measurements"], results[log_name]["after"]["measurements"]):
                for field in ("filter", "pass", "digest", "traces", "events"):
                    if before[field] != after[field]:
                        raise AssertionError(f"Parity failed: {log_name} {before['filter']} {field}")
    print(f"All {12 * len(args.logs)} paired filter runs preserve trace/event/attribute content and source logs.", flush=True)


if __name__ == "__main__":
    main()
