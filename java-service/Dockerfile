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
COPY --from=build /app/target/prom-service-0.1.0.jar /app/prom-service.jar
COPY --from=build /app/target/dependency /app/dependency
COPY java-service/lib /app/lib

ENV PORT=7070
ENV LOGS_ROOT=/data/logs

EXPOSE 7070

CMD ["sh", "-c", "java -cp /app/prom-service.jar:/app/dependency/*:/app/lib/* PromService"]
