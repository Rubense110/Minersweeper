package com.minersweeper.javaservice.evaluation.isolation;

import com.minersweeper.javaservice.api.dto.*;
import com.minersweeper.javaservice.artifacts.ArtifactStore;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Actual subprocess, including an uncooperative thread and an OS descendant. */
public final class IsolatedWorkerFixture {
    public static void main(String[] args) throws Exception {
        Path home=Paths.get(args[0]);
        if (Files.exists(home.getParent().resolve("fail-next-start"))) Runtime.getRuntime().halt(18);
        ArtifactStore store=new ArtifactStore(home.resolve("artifacts").toString());
        Files.write(home.resolve("ready"),new byte[]{1});
        BufferedReader input=new BufferedReader(new InputStreamReader(System.in,"UTF-8"));
        String name;
        while ((name=input.readLine())!=null) {
            WorkerProtocol.Command c=WorkerProtocol.JSON.readValue(home.resolve(name).toFile(),WorkerProtocol.Command.class);
            WorkerProtocol.Reply r=new WorkerProtocol.Reply();
            if (!"cleanup".equals(c.operation)) {
                if ("exit".equals(c.request.log_path)) Runtime.getRuntime().halt(17);
                Map<String,Double> metrics=new LinkedHashMap<String,Double>(); metrics.put("fitness",.8);
                r.result=store.store(c.request,metrics,"<pnml>original-τ</pnml>","fixed",3,1,true,Collections.emptyList(),
                    Arrays.asList(new ArtifactBulkResponse.MarkingEntry("p0",2)),
                    Arrays.asList(new ArtifactBulkResponse.MarkingEntry("pf",3)),
                    Arrays.asList(Arrays.asList(new ArtifactBulkResponse.MarkingEntry("pf",3)),Collections.emptyList()),
                    Arrays.asList(new ArtifactBulkResponse.TransitionEntry("t","route",true)));
                if ("hang-and-break-replacement".equals(c.request.log_path)) Files.write(home.getParent().resolve("fail-next-start"),new byte[]{1});
                if (c.request.log_path.startsWith("hang")) {
                    new ProcessBuilder("sleep","300").start();
                    Files.write(home.resolve("hanging"),new byte[]{1});
                    for (;;) { try { Thread.sleep(100); } catch (InterruptedException ignored) {} }
                }
                if ("slow".equals(c.request.log_path)) Thread.sleep(400);
            }
            WorkerProtocol.publish(home.resolve(name+".reply"),r);
        }
    }
}
