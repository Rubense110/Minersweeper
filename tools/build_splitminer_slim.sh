#!/usr/bin/env bash
set -euo pipefail

PROM_HOME=${PROM_HOME:-tools/prom-lite-1.4-all-platforms}
SPLIT_DIR="${PROM_HOME}/packages/splitminer-1.7.1"
ALL_JAR="${SPLIT_DIR}/split-miner-1.7.1-all.jar"
SLIM_JAR="${SPLIT_DIR}/split-miner-1.7.1-slim.jar"
FORCE=${FORCE:-0}

ALL_JAR_ABS="$(cd "$(dirname "${ALL_JAR}")" && pwd)/$(basename "${ALL_JAR}")"
SLIM_JAR_ABS="$(cd "$(dirname "${SLIM_JAR}")" && pwd)/$(basename "${SLIM_JAR}")"

if [[ ! -f "${ALL_JAR_ABS}" ]]; then
  echo "SplitMiner all jar not found: ${ALL_JAR_ABS}" >&2
  exit 1
fi

if [[ -f "${SLIM_JAR_ABS}" && "${FORCE}" != "1" ]]; then
  echo "Slim jar already exists: ${SLIM_JAR_ABS}"
  echo "Use FORCE=1 to regenerate."
  exit 0
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

mkdir -p "${tmp_dir}/unpacked"

echo "Building SplitMiner slim jar..."
echo "PROM_HOME=${PROM_HOME}"

( cd "${tmp_dir}/unpacked" && jar xf "${ALL_JAR_ABS}" )

# Remove only the replay-result classes that conflict at runtime with
# PNetReplayer/PNetAlignmentAnalysis (PNRepResult interface vs class).
rm -rf "${tmp_dir}/unpacked/org/processmining/plugins/astar"
rm -rf "${tmp_dir}/unpacked/org/processmining/plugins/connectionfactories/logpetrinet"
rm -rf "${tmp_dir}/unpacked/org/processmining/plugins/petrinet/replayer"
rm -rf "${tmp_dir}/unpacked/org/processmining/plugins/petrinet/replayresult"
rm -rf "${tmp_dir}/unpacked/org/processmining/plugins/replayer/replayresult"

rm -f "${tmp_dir}/unpacked"/META-INF/*.SF "${tmp_dir}/unpacked"/META-INF/*.RSA "${tmp_dir}/unpacked"/META-INF/*.DSA || true

jar cfm "${SLIM_JAR_ABS}" "${tmp_dir}/unpacked/META-INF/MANIFEST.MF" -C "${tmp_dir}/unpacked" .

echo "Created ${SLIM_JAR_ABS}"
echo "Removed conflicting packages:"
echo "  - org/processmining/plugins/astar"
echo "  - org/processmining/plugins/connectionfactories/logpetrinet"
echo "  - org/processmining/plugins/petrinet/replayer"
echo "  - org/processmining/plugins/petrinet/replayresult"
echo "  - org/processmining/plugins/replayer/replayresult"

if jar tf "${SLIM_JAR_ABS}" | grep -q 'org/processmining/plugins/petrinet/replayresult/PNRepResult.class'; then
  echo "ERROR: slim jar still contains PNRepResult; build is invalid." >&2
  exit 1
fi

if ! jar tf "${SLIM_JAR_ABS}" | grep -q 'processmining/splitminer/SplitMiner.class'; then
  echo "ERROR: slim jar does not contain SplitMiner.class; build is invalid." >&2
  exit 1
fi

if ! jar tf "${SLIM_JAR_ABS}" | grep -q 'org/processmining/models/graphbased/directed/bpmn/BPMNDiagram.class'; then
  echo "ERROR: slim jar does not contain BPMNDiagram.class; build is invalid." >&2
  exit 1
fi

echo "Sanity checks passed: PNRepResult removed, SplitMiner.class and BPMNDiagram.class present."
