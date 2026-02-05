#!/usr/bin/env bash
set -euo pipefail

PROM_HOME=${PROM_HOME:-prom-lite-1.4-all-platforms}

if [[ ! -d "$PROM_HOME" ]]; then
  echo "PROM_HOME not found: $PROM_HOME" >&2
  exit 1
fi

install() {
  local file="$1"
  local group="$2"
  local artifact="$3"
  local version="$4"

  if [[ ! -f "$file" ]]; then
    echo "Missing jar: $file" >&2
    exit 1
  fi

  mvn install:install-file \
    -Dfile="$file" \
    -DgroupId="$group" \
    -DartifactId="$artifact" \
    -Dversion="$version" \
    -Dpackaging=jar \
    -DgeneratePom=true
}

install "$PROM_HOME/packages/alphaminer-6.9.78/AlphaMiner.jar" prom AlphaMiner 6.9.78
install "$PROM_HOME/packages/prom-framework-6.10.110/ProM-Framework.jar" prom ProM-Framework 6.10.110
install "$PROM_HOME/packages/prom-contexts-6.10.62/ProM-Contexts.jar" prom ProM-Contexts 6.10.62
install "$PROM_HOME/packages/prom-plugins-6.9.70/ProM-Plugins.jar" prom ProM-Plugins 6.9.70
install "$PROM_HOME/packages/log-6.12.2/Log.jar" prom Log 6.12.2
install "$PROM_HOME/packages/petrinets-6.10.158/PetriNets.jar" prom PetriNets 6.10.158
install "$PROM_HOME/packages/log-6.12.2/lib/OpenXES-20211004.jar" org.deckfour openxes 20211004

install "$PROM_HOME/lib/Uitopia-0.6-20190913.jar" prom.thirdparty Uitopia 0.6-20190913
install "$PROM_HOME/lib/UITopiaResources-0.6-20190913.jar" prom.thirdparty UITopiaResources 0.6-20190913
install "$PROM_HOME/lib/jgraph-5.13.0.4.jar" prom.thirdparty jgraph 5.13.0.4
install "$PROM_HOME/lib/slickerbox-1.0rc1.jar" prom.thirdparty slickerbox 1.0rc1
install "$PROM_HOME/lib/guava-16.0.1.jar" com.google.guava guava 16.0.1
install "$PROM_HOME/lib/commons-logging-1.1.3.jar" commons-logging commons-logging 1.1.3
install "$PROM_HOME/lib/commons-compress-1.13.jar" org.apache.commons commons-compress 1.13
install "$PROM_HOME/lib/bsh-2.0b4.jar" org.beanshell bsh 2.0b4
install "$PROM_HOME/lib/jargs-latest.jar" jargs jargs latest
install "$PROM_HOME/lib/TableLayout-20050920.jar" prom.thirdparty TableLayout 20050920
install "$PROM_HOME/lib/Spex-1.1.jar" prom.thirdparty Spex 1.1

printf "\nDone. You can now add the dependencies to java-service/pom.xml.\n"
