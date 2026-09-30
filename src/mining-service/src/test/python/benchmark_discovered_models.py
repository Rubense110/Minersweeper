#!/usr/bin/env python3
"""Compare legacy/current replay on the same persisted discovered Petri nets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from benchmark_token_precision import JAVA_PROBE

JAVA = JAVA_PROBE[:JAVA_PROBE.index(" public static void main")].replace("PrecisionComparison", "DiscoveredModelComparison") + r"""
 static Marking marking(com.fasterxml.jackson.databind.JsonNode entries, java.util.Map<String, Place> places) {
  Marking marking = new Marking();
  for (com.fasterxml.jackson.databind.JsonNode entry : entries) marking.add(places.get(entry.get("place_id").asText()), entry.get("tokens").asInt());
  return marking;
 }
 public static void main(String[] args) throws Exception {
  XLog log = readNames(args[0]);
  com.fasterxml.jackson.databind.JsonNode solutions = new com.fasterxml.jackson.databind.ObjectMapper().readTree(new File(args[1]));
  XEventNameClassifier classifier = new XEventNameClassifier();
  XEventClasses classes = XLogInfoFactory.createLogInfo(log, classifier).getEventClasses();
  int checked = 0;
  for (com.fasterxml.jackson.databind.JsonNode solution : solutions) {
   if (!solution.has("places") || solution.get("places").size() == 0) continue;
   Petrinet net = PetrinetFactory.newPetrinet("persisted-model");
   java.util.Map<String, Place> places = new java.util.LinkedHashMap<String, Place>();
   java.util.Map<String, Transition> transitions = new java.util.LinkedHashMap<String, Transition>();
   TransEvClassMapping mapping = new TransEvClassMapping(classifier, new XEventClass("DUMMY", -1));
   for (com.fasterxml.jackson.databind.JsonNode entry : solution.get("places")) places.put(entry.get("id").asText(), net.addPlace(entry.path("label").asText()));
   for (com.fasterxml.jackson.databind.JsonNode entry : solution.get("transitions")) {
    Transition transition = net.addTransition(entry.path("label").asText()); transition.setInvisible(entry.path("invisible").asBoolean()); transitions.put(entry.get("id").asText(), transition);
    XEventClass eventClass = classes.getByIdentity(transition.getLabel());
    if (eventClass == null) eventClass = classes.getByIdentity(transition.getLabel() + "+complete");
    mapping.put(transition, eventClass == null ? mapping.getDummyEventClass() : eventClass);
   }
   for (com.fasterxml.jackson.databind.JsonNode entry : solution.get("arcs")) {
    String source = entry.get("source").asText(), target = entry.get("target").asText();
    if (places.containsKey(source)) net.addArc(places.get(source), transitions.get(target)); else net.addArc(transitions.get(source), places.get(target));
   }
   Marking initial = marking(solution.get("initial_marking"), places);
   java.util.List<Marking> finals = new java.util.ArrayList<Marking>();
   for (com.fasterxml.jackson.databind.JsonNode entry : solution.get("final_markings")) finals.add(marking(entry, places));
   TokenReplayResult oldFitness = new LegacyTokenReplayComputation(log, net, initial, finals, classifier, mapping, null).compute();
   TokenReplayResult newFitness = new TokenReplayComputation(log, net, initial, finals, classifier, mapping, null).compute();
   if (oldFitness.missing()!=newFitness.missing() || oldFitness.consumed()!=newFitness.consumed() || oldFitness.remaining()!=newFitness.remaining() || oldFitness.produced()!=newFitness.produced() || oldFitness.fitTraceCount()!=newFitness.fitTraceCount() || !oldFitness.transitionActivations().equals(newFitness.transitionActivations())) throw new AssertionError("fitness counters/activations differ at model " + checked);
   TokenReplayPrecisionResult oldPrecision = new LegacyTokenReplayPrecisionComputation(log, new LegacyTokenReplayEngine(net, initial, finals.get(0), classifier, mapping), null).compute();
   TokenReplayPrecisionResult newPrecision = new TokenReplayPrecisionComputation(log, new TokenReplayEngine(net, initial, finals.get(0), classifier, mapping), null).compute();
   if (oldPrecision.prefixCount()!=newPrecision.prefixCount() || oldPrecision.replayedPrefixCount()!=newPrecision.replayedPrefixCount() || oldPrecision.activatedTransitions()!=newPrecision.activatedTransitions() || oldPrecision.escapingEdges()!=newPrecision.escapingEdges()) throw new AssertionError("precision counters differ at model " + checked);
   checked++;
   System.out.println("PASS model="+checked+" transitions="+transitions.size()+" fitness="+newFitness.fitness()+" precision="+newPrecision.precision());
  }
  System.out.println("CHECKED=" + checked);
 }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--baseline", default="de3d395")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    result = json.loads(args.result.read_text())
    solutions = result["optimization"]["solutions"]["solutions"]
    prom = root / "tools/prom-lite-1.4-all-platforms"
    jars = sorted(str(path) for base in (prom / "lib", prom / "packages") for path in base.rglob("*.jar") if path.name != "split-miner-1.7.1-all.jar")
    classpath = ":".join([str(root / "src/mining-service/target/classes"), str(root / "src/mining-service/target/dependency/*")] + jars)
    source_root = "src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/conformance/"
    with tempfile.TemporaryDirectory(prefix="minersweeper-discovered-") as temporary:
        output = Path(temporary)
        for name in ("TokenReplayEngine", "TokenReplayComputation", "TokenReplayPrecisionComputation"):
            code = subprocess.check_output(["git", "show", args.baseline + ":" + source_root + name + ".java"], cwd=root, text=True)
            for target in ("TokenReplayPrecisionComputation", "TokenReplayComputation", "TokenReplayEngine"):
                code = code.replace(target, "Legacy" + target)
            (output / ("Legacy" + name + ".java")).write_text(code)
        (output / "DiscoveredModelComparison.java").write_text(JAVA)
        (output / "solutions.json").write_text(json.dumps(solutions))
        subprocess.run(["javac", "-cp", classpath, "-d", temporary] + [str(path) for path in output.glob("*.java")], check=True)
        subprocess.run(["java", "-Xmx768m", "-Djava.awt.headless=true", "-cp", temporary + ":" + classpath, "com.minersweeper.javaservice.evaluation.conformance.DiscoveredModelComparison", str(root / "event_logs" / result["log"]), str(output / "solutions.json")], check=True)


if __name__ == "__main__":
    main()
