#!/usr/bin/env bash
set -euo pipefail

PROM_HOME=${PROM_HOME:-prom-lite-1.4-all-platforms}
REPO_LOCAL=${REPO_LOCAL:-$HOME/.m2/repository}
MVN=${MVN:-mvn}

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

  "$MVN" -Dmaven.repo.local="$REPO_LOCAL" install:install-file \
    -Dfile="$file" \
    -DgroupId="$group" \
    -DartifactId="$artifact" \
    -Dversion="$version" \
    -Dpackaging=jar \
    -DgeneratePom=true
}

install "$PROM_HOME/packages/alphaminer-6.9.78/AlphaMiner.jar" prom AlphaMiner 6.9.78
install "$PROM_HOME/packages/acceptingpetrinet-6.11.196/AcceptingPetriNet.jar" prom AcceptingPetriNet 6.11.196
install "$PROM_HOME/packages/basicutils-6.9.126/BasicUtils.jar" prom BasicUtils 6.9.126
install "$PROM_HOME/packages/inductiveminer-6.10.566/InductiveMiner.jar" prom InductiveMiner 6.10.566
install "$PROM_HOME/packages/inductiveminerdeprecated-6.10.72/InductiveMinerDeprecated.jar" prom InductiveMinerDeprecated 6.10.72
install "$PROM_HOME/packages/heuristicsminer-6.10.78/HeuristicsMiner.jar" prom HeuristicsMiner 6.10.78
SPLITMINER_SLIM_JAR="$PROM_HOME/packages/splitminer-1.7.1/split-miner-1.7.1-slim.jar"
if [[ ! -f "$SPLITMINER_SLIM_JAR" ]]; then
  echo "Missing SplitMiner slim jar: $SPLITMINER_SLIM_JAR" >&2
  echo "Generate it once with: ./tools/build_splitminer_slim.sh" >&2
  exit 1
fi
install "$SPLITMINER_SLIM_JAR" prom SplitMiner 1.7.1
install "$PROM_HOME/packages/ilpminer-6.9.62/ILPMiner.jar" prom ILPMiner 6.9.62
install "$PROM_HOME/packages/hybridilpminer-6.10.154/HybridILPMiner.jar" prom HybridILPMiner 6.10.154
install "$PROM_HOME/packages/lpengine-6.9.90/LPEngine.jar" prom LPEngine 6.9.90
install "$PROM_HOME/packages/efficientstorage-6.9.126/EfficientStorage.jar" prom EfficientStorage 6.9.126
install "$PROM_HOME/packages/lpsolve-5.5.4/lib/lpsolve55j.jar" prom.thirdparty lpsolve55j 5.5.4
install "$PROM_HOME/packages/pnetreplayer-6.9.179/PNetReplayer.jar" prom PNetReplayer 6.9.179
install "$PROM_HOME/packages/pnetalignmentanalysis-6.10.114/PNetAlignmentAnalysis.jar" prom PNetAlignmentAnalysis 6.10.114
install "$PROM_HOME/packages/prom-framework-6.10.110/ProM-Framework.jar" prom ProM-Framework 6.10.110
install "$PROM_HOME/packages/prom-contexts-6.10.62/ProM-Contexts.jar" prom ProM-Contexts 6.10.62
install "$PROM_HOME/packages/prom-models-6.10.40/ProM-Models.jar" prom ProM-Models 6.10.40
install "$PROM_HOME/packages/prom-plugins-6.9.70/ProM-Plugins.jar" prom ProM-Plugins 6.9.70
install "$PROM_HOME/packages/log-6.12.2/Log.jar" prom Log 6.12.2
install "$PROM_HOME/packages/logabstractions-6.9.72/LogAbstractions.jar" prom LogAbstractions 6.9.72
install "$PROM_HOME/packages/petrinets-6.10.158/PetriNets.jar" prom PetriNets 6.10.158
install "$PROM_HOME/packages/log-6.12.2/lib/OpenXES-20211004.jar" org.deckfour openxes 20211004
install "$PROM_HOME/packages/widgets-6.11.245/Widgets.jar" prom Widgets 6.11.245

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
printf "Local Maven repository used: %s\n" "$REPO_LOCAL"
