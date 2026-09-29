#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROM_HOME="${PROM_HOME:-${ROOT_DIR}/tools/prom-lite-1.4-all-platforms}"

cd "${SCRIPT_DIR}"
mvn -q -DskipTests test-compile dependency:copy-dependencies -DincludeScope=test

# Match run_prom_service.sh: ProM's package-local libraries are not declared in Maven.
PROM_JARS="$(find "${PROM_HOME}/lib" "${PROM_HOME}/packages" -type f -name '*.jar' \
  ! -path "${PROM_HOME}/packages/splitminer-1.7.1/split-miner-1.7.1-all.jar" \
  | sort | paste -sd: -)"
NATIVE_DIRS="$(find "${PROM_HOME}" -type f \( -name '*.so' -o -name '*.dylib' -o -name '*.dll' \) \
  -printf '%h\n' | sort -u | paste -sd: -)"
CLASSPATH="target/classes:target/test-classes:target/dependency/*:${PROM_JARS}"

exec env RUN_REAL_PROM_TESTS=1 LD_LIBRARY_PATH="${NATIVE_DIRS}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
  java -Djava.awt.headless=true -Djava.library.path="${NATIVE_DIRS}" \
  -cp "${CLASSPATH}" org.junit.runner.JUnitCore PromPipelineEvaluatorRealTest
