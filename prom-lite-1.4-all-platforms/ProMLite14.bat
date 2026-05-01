@GOTO start

:add
 @set X=%X%;%1
 @GOTO :eof

:start
@set X=.\dist\ProM-Framework-6.13.6.jar
@set X=%X%;.\dist\ProM-Contexts-6.13.4.jar
@set X=%X%;.\dist\ProM-Models-6.12.1.jar
@set X=%X%;.\dist\ProM-Plugins-6.12.1.jar

@for /R .\lib %%I IN ("*.jar") DO @call :add .\lib\%%~nI.jar

@java^
 -Xmx4G^
 -da^
 -classpath "%X%"^
 -Djava.library.path=.//lib^
 -Djava.system.class.loader=org.processmining.framework.util.ProMClassLoader^
 -Djava.util.Arrays.useLegacyMergeSort=true^
 org.processmining.contexts.uitopia.UI

set X=
