#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROM_HOME="${PROM_HOME:-${ROOT_DIR}/prom-lite-1.4-all-platforms}"
PORT="${PORT:-7070}"
LOGS_ROOT="${LOGS_ROOT:-${ROOT_DIR}/event_logs}"

if [[ ! -f "${SCRIPT_DIR}/target/prom-service-0.1.0.jar" ]]; then
  echo "Missing jar: ${SCRIPT_DIR}/target/prom-service-0.1.0.jar"
  echo "Run: cd java-service && mvn -DskipTests package dependency:copy-dependencies"
  exit 1
fi

if [[ ! -d "${PROM_HOME}" ]]; then
  echo "PROM_HOME not found: ${PROM_HOME}"
  exit 1
fi

PROM_JARS="$(find "${PROM_HOME}/lib" "${PROM_HOME}/packages" -type f -name '*.jar' \
  ! -path "${PROM_HOME}/packages/splitminer-1.7.1/split-miner-1.7.1-all.jar" \
  | sort | paste -sd: -)"
BASE_CP="${SCRIPT_DIR}/target/prom-service-0.1.0.jar:${SCRIPT_DIR}/target/dependency/*"
CLASSPATH="${BASE_CP}:${PROM_JARS}"
NATIVE_DIRS="$(find "${PROM_HOME}" -type f \( -name '*.so' -o -name '*.dylib' -o -name '*.dll' \) -printf '%h\n' | sort -u | paste -sd: -)"
JAVA_LIBRARY_PATH="${NATIVE_DIRS}"
if [[ -n "${JAVA_LIBRARY_PATH_EXTRA:-}" ]]; then
  JAVA_LIBRARY_PATH="${JAVA_LIBRARY_PATH}:${JAVA_LIBRARY_PATH_EXTRA}"
fi
if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
  LD_LIBRARY_PATH="${JAVA_LIBRARY_PATH}:${LD_LIBRARY_PATH}"
else
  LD_LIBRARY_PATH="${JAVA_LIBRARY_PATH}"
fi

echo "Starting PromService on port ${PORT}"
echo "Using PROM_HOME=${PROM_HOME}"
echo "Using LOGS_ROOT=${LOGS_ROOT}"

cd "${SCRIPT_DIR}"
exec env \
  PORT="${PORT}" \
  LOGS_ROOT="${LOGS_ROOT}" \
  LD_LIBRARY_PATH="${LD_LIBRARY_PATH}" \
  java -Djava.library.path="${JAVA_LIBRARY_PATH}" -cp "${CLASSPATH}" com.minersweeper.javaservice.app.PromService
