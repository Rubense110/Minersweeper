#!/bin/sh

###
## ProM specific
###
PROGRAM=ProM
CP=./dist/ProM-Framework-6.13.6.jar:./dist/ProM-Contexts-6.13.4.jar:./dist/ProM-Models-6.12.1.jar:./dist/ProM-Plugins-6.12.1.jar
LIBDIR=./lib
MAIN=org.processmining.contexts.uitopia.UI

####
## Environment options
###
JAVA=java

###
## Main program
###

add() {
	CP=${CP}:$1
}


for lib in $LIBDIR/*.jar
do
	add $lib
done

$JAVA\
 -Xmx4G\
 -da\
 -classpath ${CP}\
 -Djava.library.path=${LIBDIR}\
 -Djava.system.class.loader=org.processmining.framework.util.ProMClassLoader\
 -Djava.util.Arrays.useLegacyMergeSort=true\
 ${MAIN}
