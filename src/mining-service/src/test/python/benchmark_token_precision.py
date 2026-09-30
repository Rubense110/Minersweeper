"""Compare baseline/current token precision on an all-activities loop net.

Compile Java tests and copy test dependencies first. This measures scoring only,
using actual concept:name sequences; it does not benchmark discovery or RSS.
Requires a HotSpot JVM with the thread allocation counter.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import tempfile

JAVA_PROBE = r"""
package com.minersweeper.javaservice.evaluation.conformance;
import java.io.File;
import org.deckfour.xes.in.XesXmlParser;
import org.deckfour.xes.model.XLog;
import org.deckfour.xes.classification.*;
import org.deckfour.xes.info.XLogInfoFactory;
import org.processmining.models.graphbased.directed.petrinet.*;
import org.processmining.models.graphbased.directed.petrinet.elements.*;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;
import org.processmining.plugins.connectionfactories.logpetrinet.TransEvClassMapping;
public class PrecisionComparison {
 static XLog readNames(String path) throws Exception {
  final org.deckfour.xes.factory.XFactory factory = org.deckfour.xes.factory.XFactoryRegistry.instance().currentDefault();
  final XLog log = factory.createLog();
  javax.xml.parsers.SAXParserFactory.newInstance().newSAXParser().parse(new File(path), new org.xml.sax.helpers.DefaultHandler() {
   org.deckfour.xes.model.XTrace trace;
   org.deckfour.xes.model.XEvent event;
   public void startElement(String uri, String local, String name, org.xml.sax.Attributes attributes) {
    if (name.equals("trace")) trace = factory.createTrace();
    if (name.equals("event")) event = factory.createEvent();
    if (name.equals("string") && event != null && "concept:name".equals(attributes.getValue("key"))) org.deckfour.xes.extension.std.XConceptExtension.instance().assignName(event, attributes.getValue("value"));
   }
   public void endElement(String uri, String local, String name) {
    if (name.equals("event")) { trace.add(event); event = null; }
    if (name.equals("trace")) { log.add(trace); trace = null; }
   }
  });
  return log;
 }
 public static void main(String[] args) throws Exception {
  XLog log = readNames(args[0]);
  XEventNameClassifier classifier = new XEventNameClassifier();
  XEventClasses classes = XLogInfoFactory.createLogInfo(log, classifier).getEventClasses();
  Petrinet net = PetrinetFactory.newPetrinet("all-activities-loop"); Place place = net.addPlace("p");
  Marking marking = new Marking(); marking.add(place);
  TransEvClassMapping mapping = new TransEvClassMapping(classifier, new XEventClass("DUMMY", -1));
  for (XEventClass eventClass : classes.getClasses()) {
   Transition transition = net.addTransition(eventClass.getId());
   net.addArc(place, transition); net.addArc(transition, place); mapping.put(transition, eventClass);
  }
  com.sun.management.ThreadMXBean bean = (com.sun.management.ThreadMXBean) java.lang.management.ManagementFactory.getThreadMXBean();
  bean.setThreadAllocatedMemoryEnabled(true); long thread = Thread.currentThread().getId();
  for (int pass = 0; pass < 2; pass++) {
   long allocated = bean.getThreadAllocatedBytes(thread), start = System.nanoTime();
   TokenReplayPrecisionResult previous = new LegacyTokenReplayPrecisionComputation(log, new LegacyTokenReplayEngine(net, marking, marking, classifier, mapping), null).compute();
   long oldNanos = System.nanoTime() - start, oldBytes = bean.getThreadAllocatedBytes(thread) - allocated;
   allocated = bean.getThreadAllocatedBytes(thread); start = System.nanoTime();
   TokenReplayPrecisionResult current = new TokenReplayPrecisionComputation(log, new TokenReplayEngine(net, marking, marking, classifier, mapping), null).compute();
   long newNanos = System.nanoTime() - start, newBytes = bean.getThreadAllocatedBytes(thread) - allocated;
   if (previous.prefixCount()!=current.prefixCount() || previous.replayedPrefixCount()!=current.replayedPrefixCount() || previous.activatedTransitions()!=current.activatedTransitions() || previous.escapingEdges()!=current.escapingEdges() || previous.precision()!=current.precision()) throw new AssertionError("counters differ");
   System.out.println("pass="+pass+" old_ms="+oldNanos/1000000+" new_ms="+newNanos/1000000+" old_allocated_bytes="+oldBytes+" new_allocated_bytes="+newBytes+" precision="+current.precision()+" prefixes="+current.prefixCount());
  }
 }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="de3d395")
    parser.add_argument("logs", nargs="*", default=["BPI_Challenge_2013_incidents.xes", "BPI_Challenge_2012.xes"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    prom = root / "tools/prom-lite-1.4-all-platforms"
    jars = sorted(str(path) for base in (prom / "lib", prom / "packages") for path in base.rglob("*.jar") if path.name != "split-miner-1.7.1-all.jar")
    classpath = ":".join([str(root / "src/mining-service/target/classes"), str(root / "src/mining-service/target/dependency/*")] + jars)
    source_root = "src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/conformance/"
    with tempfile.TemporaryDirectory(prefix="minersweeper-precision-") as temporary:
        output = Path(temporary)
        for name in ("TokenReplayEngine", "TokenReplayPrecisionComputation"):
            code = subprocess.check_output(["git", "show", args.baseline + ":" + source_root + name + ".java"], cwd=root, text=True)
            for target in ("TokenReplayPrecisionComputation", "TokenReplayEngine"):
                code = code.replace(target, "Legacy" + target)
            (output / ("Legacy" + name + ".java")).write_text(code)
        (output / "PrecisionComparison.java").write_text(JAVA_PROBE)
        subprocess.run(["javac", "-cp", classpath, "-d", temporary] + [str(path) for path in output.glob("*.java")], check=True)
        for name in args.logs:
            log = Path(name)
            if not log.is_absolute():
                log = root / "event_logs" / log
            print("LOG=" + str(log), flush=True)
            subprocess.run(["java", "-Xmx2g", "-Djava.awt.headless=true", "-cp", temporary + ":" + classpath, "com.minersweeper.javaservice.evaluation.conformance.PrecisionComparison", str(log)], check=True)


if __name__ == "__main__":
    main()
