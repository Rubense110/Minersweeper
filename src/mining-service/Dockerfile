FROM maven:3.9.9-eclipse-temurin-8 AS build

WORKDIR /app

COPY tools/install_prom_jars.sh /app/tools/install_prom_jars.sh
COPY tools/prom-lite-1.4-all-platforms /app/tools/prom-lite-1.4-all-platforms
COPY src/mining-service/pom.xml /app/pom.xml
COPY src/mining-service/src /app/src

RUN chmod +x /app/tools/install_prom_jars.sh \
  && PROM_HOME=/app/tools/prom-lite-1.4-all-platforms /app/tools/install_prom_jars.sh \
  && mvn -q -DskipTests package \
  && mvn -q -DskipTests dependency:copy-dependencies -DincludeScope=runtime

FROM eclipse-temurin:8-jre

WORKDIR /app
COPY --from=build /app/tools/prom-lite-1.4-all-platforms /app/tools/prom-lite-1.4-all-platforms

# Keep runtime layout compatible with run_prom_service.sh.
COPY --from=build /app/target/prom-service-0.1.0.jar /app/mining-service/target/prom-service-0.1.0.jar
COPY --from=build /app/target/dependency /app/mining-service/target/dependency
COPY src/mining-service/run_prom_service.sh /app/mining-service/run_prom_service.sh
COPY src/mining-service/lib /app/mining-service/lib
RUN chmod +x /app/mining-service/run_prom_service.sh

ENV PORT=7070
ENV LOGS_ROOT=/data/logs
ENV PROM_HOME=/app/tools/prom-lite-1.4-all-platforms

EXPOSE 7070

WORKDIR /app/mining-service
CMD ["./run_prom_service.sh"]
