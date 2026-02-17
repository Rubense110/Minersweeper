FROM maven:3.9.9-eclipse-temurin-8 AS build

WORKDIR /app

COPY install_prom_jars.sh /app/install_prom_jars.sh
COPY prom-lite-1.4-all-platforms /app/prom-lite-1.4-all-platforms
COPY java-service/pom.xml /app/pom.xml
COPY java-service/src /app/src

RUN chmod +x /app/install_prom_jars.sh \
  && /app/install_prom_jars.sh \
  && mvn -q -DskipTests package \
  && mvn -q -DskipTests dependency:copy-dependencies -DincludeScope=runtime

FROM eclipse-temurin:8-jre

WORKDIR /app
COPY --from=build /app/prom-lite-1.4-all-platforms /app/prom-lite-1.4-all-platforms

# Keep runtime layout compatible with run_prom_service.sh.
COPY --from=build /app/target/prom-service-0.1.0.jar /app/java-service/target/prom-service-0.1.0.jar
COPY --from=build /app/target/dependency /app/java-service/target/dependency
COPY java-service/run_prom_service.sh /app/java-service/run_prom_service.sh
COPY java-service/lib /app/java-service/lib
RUN chmod +x /app/java-service/run_prom_service.sh

ENV PORT=7070
ENV LOGS_ROOT=/data/logs
ENV PROM_HOME=/app/prom-lite-1.4-all-platforms

EXPOSE 7070

WORKDIR /app/java-service
CMD ["./run_prom_service.sh"]
