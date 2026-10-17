package com.minersweeper.javaservice.evaluation.reproducibility;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.stream.Stream;

/** Fingerprints the loaded build/dependency classpath once; no absolute paths in the digest. */
public final class EvaluationEnvironment {
    private static volatile Map<String,String> cached;
    private EvaluationEnvironment() {}

    public static Map<String,String> current() throws IOException {
        Map<String,String> result = cached;
        if (result != null) return result;
        synchronized (EvaluationEnvironment.class) {
            if (cached != null) return cached;
            Map<String,String> values = new LinkedHashMap<String,String>();
            values.put("java_version", System.getProperty("java.version"));
            values.put("java_vendor", System.getProperty("java.vendor"));
            values.put("architecture", System.getProperty("os.arch"));
            String isolation = System.getenv("PROM_EVALUATION_ISOLATION_POLICY");
            values.put("evaluation_isolation_policy", isolation == null ? "in-process" : isolation);
            values.put("canonical_net_version", CanonicalNetOrder.VERSION);
            SplitMinerProvenance.verify();
            values.put("split_discovery_policy_version", SplitMinerProvenance.VERSION);
            values.put("prom_allow_miner_multithreading", Boolean.toString(
                Boolean.parseBoolean(System.getenv("PROM_ALLOW_MINER_MULTITHREADING"))));
            MessageDigest digest;
            try { digest = MessageDigest.getInstance("SHA-256"); }
            catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
            // Preserve class-loader precedence. JVM expands classpath wildcards.
            for (String entry : System.getProperty("java.class.path", "").split(File.pathSeparator)) {
                Path path = Paths.get(entry);
                if (Files.isRegularFile(path)) {
                    hashFile(digest, path.getFileName().toString(), path);
                } else if (Files.isDirectory(path)) {
                    List<Path> classes = new ArrayList<Path>();
                    try (Stream<Path> paths = Files.walk(path)) {
                        paths.filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".class")).forEach(classes::add);
                    }
                    Collections.sort(classes);
                    for (Path p : classes) hashFile(digest, path.relativize(p).toString(), p);
                }
            }
            StringBuilder hex = new StringBuilder();
            for (byte v : digest.digest()) hex.append(String.format("%02x", v & 255));
            values.put("java_classpath_sha256", hex.toString());
            cached = Collections.unmodifiableMap(values);
            return cached;
        }
    }

    private static void hashFile(MessageDigest digest, String name, Path path) throws IOException {
        digest.update(name.getBytes(StandardCharsets.UTF_8)); digest.update((byte) 0);
        digest.update(Long.toString(Files.size(path)).getBytes(StandardCharsets.UTF_8)); digest.update((byte) 0);
        try (InputStream stream = Files.newInputStream(path)) {
            byte[] chunk = new byte[65536]; int read;
            while ((read = stream.read(chunk)) != -1) {
                ExecutionChecks.check(); digest.update(chunk, 0, read);
            }
        }
    }
}
