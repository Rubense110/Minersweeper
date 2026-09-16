# Plan de implementación: semántica de modelos, factibilidad y Pareto

## Estado del análisis

Este plan se preparó contra el commit `d211175` de la rama `features-rework`, tomando como especificación `minersweeper-rework-context.md`.

No se ha modificado código de producción ni de tests. El único cambio realizado durante el análisis es la creación de este documento.

La base actual está verde:

- servicio Python: 99 tests superados con `python -m unittest discover -s src/optimization-service/tests -p 'test_*.py'`;
- servicio Java: 57 tests superados con `mvn test -q`; el test real de ProM queda omitido si no se define `RUN_REAL_PROM_TESTS=1`.

## Conclusión ejecutiva

El repositorio ya contiene una primera implementación de markings e invisibilidad, pero todavía no cumple el documento de rework:

1. Los markings se guardan, pero Java puede inventarlos a partir de source/sink places y Python vuelve a inferirlos desde PNML si faltan.
2. La invisibilidad persistida se obtiene del PNML y, si no aparece explícita, se infiere desde etiquetas como `tau` o `silent`.
3. La optimización declara `number_of_constraints() == 0`; un modelo sin transiciones visibles es hoy un candidato normal.
4. El frente final usa ranking exclusivamente por objetivos. Además, los snapshots tienen un defecto independiente: `_non_dominated_evaluation_ids()` devuelve todos los IDs recibidos y marca toda la población del snapshot como Pareto.
5. El flujo de métricas sí pasa el log original a fitness, precision y generalisation; simplicity es puramente estructural. No se ha encontrado ninguna rama que pase deliberadamente `processedLog` al cálculo final.
6. La seed gobierna la evolución Python, pero no se envía al servicio Java ni a los miners. El Inductive Miner usa multithreading por defecto y hay evaluaciones concurrentes, por lo que la seed maestra no garantiza reproducibilidad integral.

## Decisiones de contrato

Para las nuevas ejecuciones se usará un contrato semántico estricto, con `model_schema_version: 2`. No se creará un nuevo envelope ni un rediseño general de serialización.

La forma canónica propuesta es:

```json
{
  "model_schema_version": 2,
  "transitions": [
    {"id": "t0", "label": "A", "invisible": false}
  ],
  "initial_marking": [
    {"place_id": "p0", "tokens": 1}
  ],
  "final_marking": [
    {"place_id": "p1", "tokens": 1}
  ],
  "final_markings": [
    [{"place_id": "p1", "tokens": 1}]
  ],
  "visible_transition_count": 1,
  "is_feasible": true,
  "constraint_violations": []
}
```

Decisiones concretas:

- Se conserva la representación existente de un marking como lista de `{place_id, tokens}`. Es equivalente al mapa recomendado por la especificación, preserva multiplicidad y minimiza migraciones.
- Se añade `final_marking` singular: será exactamente el marking que recibe la evaluación de conformidad.
- Se conserva `final_markings` para no perder los accepting markings adicionales de un `AcceptingPetriNet` y para compatibilidad.
- Los nuevos exports escribirán `transition.invisible`. `is_invisible` solo se aceptará al leer resultados de esquema anterior.
- Un marking vacío no se tratará como “ausente”. `null`/ausencia y un `Marking` real vacío son estados distintos.
- Los resultados de versión 2 nunca inferirán markings ni invisibilidad. Si el miner/contexto no ofrece semántica real, la evaluación fallará de forma explícita en vez de fabricar source/sink markings.
- Las filas antiguas se mantendrán legibles como esquema 1. No se reclasificarán automáticamente modelos históricos porque su invisibilidad no es fiable.
- No se añadirá peso a los arcos. Los arcos seguirán siendo entidades individuales con `id`, `source` y `target`.

## Flujo actual de extremo a extremo

```text
RunPage.jsx
  -> POST /optimizations
  -> OptimizationJobManager.submit
  -> api.manager_runtime.execute_job
  -> OptimizedProcessMiner.discover
  -> PipelineOptimizationProblem.evaluate
  -> ProMServiceClient.evaluate_pipeline
  -> POST Java /pipeline
  -> PromPipelineEvaluator.evaluate
       LogLoader.loadForExperiment              -> log original
       PreprocessingPipeline.apply(log)          -> processedLog
       discoverModel(processedLog)               -> DiscoveryArtifact
       ConformanceMetricsCalculator.compute(log) -> métricas contra original
       ArtifactStore.store                       -> PNML + metadata temporal
  <- metrics/evaluation_id
  -> NSGA-III y ranking final
  -> manager_runtime serializa población/snapshots
  -> manager_persistence.fetch_artifacts
  -> petri._petri_from_pnml
  -> JobStore (PostgreSQL/SQLite)
  -> API / CSV / ResultsPage
```

Los artifacts Java se eliminan después de persistir el experimento; por eso la base Python y el ZIP son el resultado duradero.

## Representación actual

### Petri net y accepting semantics en Java

- `org.processmining.models.graphbased.directed.petrinet.Petrinet` representa places, transitions y arcs.
- `org.processmining.models.semantics.petrinet.Marking` es un multiset. `baseSet()` enumera places y `occurrences(place)` conserva el número de tokens.
- `org.processmining.models.graphbased.directed.petrinet.elements.Transition.isInvisible()` es la fuente semántica real de invisibilidad.
- `DiscoveryArtifact` guarda `Petrinet net`, `Marking initialMarking`, `List<Marking> finalMarkings` y el PNML.
- `DiscoveryArtifact.getFinalMarking()` elige el primer final marking, y ese es el único que actualmente recibe `ConformanceMetricsCalculator`.
- `DiscoveryArtifactFactory.fromResultArray()` extrae un `AcceptingPetriNet`, un `Petrinet` y/o `Marking` del resultado del miner.
- Problema actual: `DiscoveryArtifactFactory.deriveInitialMarking()` y `deriveFinalMarking()` usan indegree/outdegree y, como fallback, el primer place. También considera un marking vacío como si faltara.

Los miners que desembocan en esa factoría son:

- `AlphaMinerDiscoverer.discover()`;
- `HeuristicsMinerDiscoverer.discover()`;
- `HybridIlpMinerDiscoverer.discover()`;
- `IlpMinerDiscoverer.discover()`;
- `InductiveMinerDiscoverer.discover()`; este ya entrega directamente un `AcceptingPetriNet`;
- `SplitMinerDiscoverer.discover()`.

Para resultados que no incluyan ambos markings en el array, la resolución permitida será consultar `InitialMarkingConnection` y `FinalMarkingConnection` del `PluginContext` para esa net. Si tampoco existen, se abortará esa evaluación. No se volverá a source/sink inference.

### Export actual

- `PromPipelineEvaluator.serializeMarking()` convierte un `Marking` a entradas `place_id`/`tokens`.
- `PromPipelineEvaluator.serializeFinalMarkings()` descarta hoy final markings vacíos.
- `ArtifactStore.store()` guarda PNML y metadata JSON temporal.
- `ArtifactBulkResponse.ArtifactEntry` y `StoredArtifactMetadata` contienen `initial_marking` y `final_markings`, pero no `final_marking`, transitions semánticas, factibilidad ni versión.
- `PmnlExporter.exportPnml()` exporta solo la `Petrinet`; los markings se guardan fuera del PNML.
- `api.manager_persistence.parse_solution_payload()` analiza places/transitions/arcs desde PNML y luego sobreescribe markings si el artifact Java los contiene.
- `api.petri._petri_from_pnml()` infiere markings ausentes por source/sink places e invisibilidad ausente por la etiqueta.
- `JobStore.Solution` y `SnapshotSolution` guardan JSON para places, transitions, arcs, `initial_marking` y `final_markings`.
- `_build_experiment_export_archive()` los exporta como celdas JSON dentro del CSV.

### Pareto actual

- `PipelineOptimizationProblem.number_of_constraints()` devuelve `0`.
- `PipelineOptimizationProblem.evaluate()` solo produce objetivos minimizados (`-metric` para métricas maximizadas).
- `PipelineNSGAIIIOptimizer` no pasa un comparator de constraints a NSGA-III.
- `PipelineNSGAIIIOptimizer._calculate_non_dominated()` usa `FastNonDominatedRanking()` con dominio solo por objetivos.
- `OptimizedProcessMiner.get_non_dominated_evaluation_ids()` obtiene los IDs del frente devuelto por el optimizer.
- `api.manager_runtime.execute_job()` construye `pareto_ids` y `_serialize_solution()` fija `is_pareto` por pertenencia del `evaluation_id`.
- En snapshots, `api.serialization._non_dominated_evaluation_ids()` no calcula dominancia: agrega todos los IDs. Por tanto, el `is_pareto` de snapshots es incorrecto incluso antes de introducir factibilidad.
- `JobStore.get_experiment_solutions(scope="pareto")` filtra el booleano persistido; no recalcula el frente.

## P0.1 — Exportar markings reales

### Cambios Java

1. `src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/discovery/DiscoveryArtifactFactory.java`
   - Reescribir `fromResultArray()` para distinguir ausencia (`null`) de marking vacío real.
   - Prioridad de resolución: `AcceptingPetriNet` -> markings explícitos del resultado -> conexiones semánticas del contexto.
   - Capturar todos los final markings suministrados, no solo el segundo `Marking` del array.
   - Eliminar `deriveInitialMarking()` y `deriveFinalMarking()`.
   - Fallar con un mensaje que incluya miner/net si falta una semántica requerida.

2. `src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/discovery/DiscoveryArtifact.java`
   - Mantener la colección completa de finals.
   - Hacer explícito el `evaluationFinalMarking` elegido una sola vez; `getFinalMarking()` y la exportación singular deben devolver el mismo objeto.
   - No filtrar markings vacíos.

3. Nuevo `src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/serialization/PetriNetSemanticsSerializer.java`
   - Mover aquí la serialización hoy privada de `PromPipelineEvaluator`.
   - `serializeMarking(Petrinet, Marking)` debe preservar multiplicidad, ordenar por ID para salida determinista y validar que cada place pertenece a la net exportada.
   - `serializeFinalMarkings(Petrinet, List<Marking>)` debe conservar cada marking, incluidos los vacíos.
   - La validación aplicará los invariantes de IDs y tokens positivos.

4. `src/mining-service/src/main/java/com/minersweeper/javaservice/evaluation/PromPipelineEvaluator.java`
   - En `evaluate()`, serializar tanto `initial_marking` como el `final_marking` usado por `ConformanceMetricsCalculator.compute()` y la lista `final_markings`.
   - Eliminar los helpers privados actuales una vez delegados al serializer.

5. Contrato y artifacts:
   - `api/dto/ArtifactBulkResponse.java`: añadir `final_marking` y `model_schema_version`.
   - `artifacts/StoredArtifactMetadata.java`: persistir ambos campos.
   - `artifacts/ArtifactStore.java`: extender ambas overloads de `store()` y `readBulk()`.
   - `api/dto/EvaluationResult.java`, `api/dto/PipelineResponse.java` y `app/http/PromHttpHandlers.java`: transportar la versión junto al resultado de evaluación.
   - `app/http/OpenApiDocs.java`: documentar el contrato v2 y marcar como requeridos los campos semánticos nuevos.

6. Los seis `*MinerDiscoverer` intervienen como productores. En principio no deben cambiar si su plugin ya devuelve APN/markings o registra conexiones. El test real por familia decidirá si alguno necesita adaptar su llamada a una variante de ProM que exponga accepting semantics; nunca se corregirá con heurísticas topológicas.

### Cambios Python/persistencia

1. `src/optimization-service/src/api/manager_persistence.py`
   - `parse_solution_payload()` usará los markings del artifact v2 como fuente autoritativa.
   - Persistirá `final_marking` además de `final_markings`.
   - Para v2, un campo semántico ausente será error de contrato, no motivo para inferir desde PNML.

2. `src/optimization-service/src/api/petri.py`
   - Separar el parser estructural de PNML de la compatibilidad legacy.
   - El camino v2 solo extraerá places/arcs (y, si se desea, comprobará consistencia), sin inventar markings.
   - `_marking_from_payload()` ya admite tanto mapa como lista y se reutilizará.
   - `_final_marking_payload()` preferirá el nuevo `final_marking`; `final_markings` queda como fallback compatible.

3. `src/optimization-service/src/job_store.py`
   - Añadir a `Solution` y `SnapshotSolution` las columnas JSON `final_marking` y la columna entera `model_schema_version`.
   - Ampliar `_ensure_schema_columns()`, escritura y serializadores.
   - Filas antiguas: versión 1 y `final_marking` derivable solo para visualización desde el primer `final_markings`; no reexportarlo como semántica v2.

4. `src/optimization-service/src/api/serialization.py`
   - Incluir `model_schema_version` y `final_marking` en CSV de soluciones y snapshots.

5. `src/optimization-service/src/api/openapi.py`, `src/frontend-service/src/pages/ResultsPage.jsx` y `src/optimization-service/src/api/petri_routes.py`
   - Exponer/consumir `final_marking` sin retirar inmediatamente `final_markings`.

### Tests

- Nuevo `DiscoveryArtifactFactoryTest.java`: APN directo, resultado con markings, conexiones de contexto, marking vacío real y fallo cuando no existe semántica.
- Nuevo `PetriNetSemanticsSerializerTest.java`: multiplicidad > 1, varios places, IDs válidos, orden estable, marking vacío y rechazo de place ajeno.
- Extender `ArtifactStoreTest.storeAndReadBulkWithPnml()` para round-trip exacto de `initial_marking`, `final_marking`, `final_markings` y versión.
- Extender `PromPipelineEvaluatorRealTest.allMinerFamiliesProduceMetricsAndArtifacts()` para comprobar que cada miner soportado produce markings reales cuyos IDs existen en el PNML.
- Extender `test_manager_persistence.py`, `test_job_store.py`, `test_api.py` y `test_petri_serialization.py` con round-trip API/DB/CSV.
- El test actual `test_petri_from_pnml_infers_missing_markings_from_source_and_sink_places` se conservará solo como prueba de lector legacy, renombrado y separado del camino v2.

## P0.2 — Exportar invisibilidad explícita

### Cambios Java

1. `PetriNetSemanticsSerializer.serializeTransitions(Petrinet)` producirá, para cada `Transition`:

   ```json
   {"id": "...", "label": "...", "invisible": true}
   ```

   La única fuente del booleano será `Transition.isInvisible()`.

2. `ArtifactBulkResponse.java`
   - Añadir `TransitionEntry { id, label, invisible }` y `ArtifactEntry.transitions`.

3. `StoredArtifactMetadata.java`, `ArtifactStore.store()/readBulk()` y `PromPipelineEvaluator.evaluate()`
   - Guardar y devolver la lista explícita junto al PNML.

4. `OpenApiDocs.java`
   - Declarar `invisible` boolean requerido para toda transition v2.

### Cambios Python/frontend

1. `api.manager_persistence.parse_solution_payload()`
   - Para artifacts v2, usar `artifact.transitions` en vez de la versión inferida por `_petri_from_pnml()`.
   - Validar que sus IDs coinciden con los IDs estructurales y los endpoints de arcs.

2. `api.petri.py`
   - `_build_petri_net_from_payload()` y `_normalize_transition_label()` leerán primero `invisible`; aceptarán `is_invisible` solo en payload legacy.
   - `_is_invisible_transition()` no participará en v2. La heurística por etiqueta quedará encapsulada exclusivamente en el lector legacy.

3. `frontend-service/src/components/PnmlViewer.jsx`
   - `parseStoredPetri()` leerá `item.invisible`, con fallback a `item.is_invisible` para datos históricos.

4. `api/openapi.py`
   - Documentar `invisible`, no `is_invisible`, como campo canónico nuevo.

### Tests

- Reutilizar `TokenReplayComputationTest.tokenReplayWalksThroughInvisibleTransitionsToEnableVisibleTransition()` como fixture semántica Java.
- Añadir al serializer Java una transition visible con etiqueta `tau` y una invisible con etiqueta arbitraria: el resultado debe respetar exclusivamente `isInvisible()`.
- Adaptar `test_petri_serialization.py`: `tau` con `invisible: false` sigue siendo visible; etiqueta arbitraria con `invisible: true` es invisible; round-trip conserva el booleano.
- Extender `test_manager_persistence.py` y `test_job_store.py` para asegurar que el campo persistido es `invisible` y de tipo booleano.
- No se añadirá un framework de tests frontend; la verificación será `npm run build` y una prueba manual breve del viewer.

## P0.3 — Constraint de cero transiciones visibles

### Punto de cálculo

La cuenta debe hacerse inmediatamente después de discovery en Java, sobre la misma `Petrinet` que se evalúa, usando:

```java
!transition.isInvisible()
```

No se calculará desde labels ni desde el JSON reconstruido posteriormente.

El modelo seguirá calculando sus métricas reales para diagnóstico; no se sustituirán por ceros. La factibilidad viajará como dimensión separada.

### Archivos y funciones

1. `PetriNetSemanticsSerializer.countVisibleTransitions(Petrinet)` o helper semántico equivalente.
2. `PromPipelineEvaluator.evaluate()`:
   - fijar `visible_transition_count`;
   - `is_feasible = visible_transition_count > 0`;
   - añadir `NO_VISIBLE_TRANSITIONS` a `constraint_violations` cuando corresponda;
   - guardar esos datos en artifact y respuesta inmediata.
3. `EvaluationResult.java`, `PipelineResponse.java`, `PromHttpHandlers.handlePipeline()`, `ArtifactBulkResponse.java`, `StoredArtifactMetadata.java`, `ArtifactStore.java` y `OpenApiDocs.java`: extender contrato y almacenamiento temporal.
4. `java_service_client.ProMServiceClient.evaluate_pipeline()`:
   - propagar los tres campos sin reinterpretarlos.
5. `problem.PipelineOptimizationProblem`:
   - `number_of_constraints()` pasará de `0` a `1`;
   - `evaluate()` pondrá `solution.constraints[0] = 0.0` si es viable y `-1.0` si viola el constraint, siguiendo la convención de jMetalPy 1.9.0;
   - copiará `is_feasible`, `constraint_violations` y `visible_transition_count` a `solution.attributes`;
   - la caché guardará/restaurará constraints y atributos, no solo objetivos;
   - un error HTTP seguirá siendo `evaluation_error`; no se confundirá con `NO_VISIBLE_TRANSITIONS`.
6. `api.serialization._serialize_solution()` y el callback de evaluación incluirán factibilidad.
7. `api.manager_persistence.py`, `job_store.py`, `api/openapi.py` y `_build_experiment_export_archive()` persistirán/expondrán:
   - `is_feasible`;
   - `constraint_violations`;
   - `visible_transition_count`.
8. Migración compatible en `JobStore._ensure_schema_columns()`:
   - las filas legacy tendrán `is_feasible = true` por compatibilidad, pero versión 1 indicará que no fue verificado con la nueva regla;
   - no se inferirá retroactivamente visibilidad para reescribir experimentos antiguos.

### Tests

- `test_problem.py`: cero transitions y tau-only devuelven constraint negativo sin alterar las métricas; una transition visible devuelve `0.0`; la caché restaura el constraint.
- Test Java del helper: net sin transitions, net tau-only y net con al menos una visible.
- `test_java_service_client.py`: propagación del metadata de factibilidad.
- `test_job_store.py` y `test_manager_persistence.py`: persistencia en soluciones finales y snapshots.

## P0.4 — Pareto consistente con factibilidad

### Cambios del optimizer

1. `src/optimization-service/src/optimizer.py`
   - Instanciar `DominanceWithConstraintsComparator` y pasarlo como `dominance_comparator` a `CancelAwareNSGAIII`.
   - Usar el mismo comparator en `_calculate_non_dominated()`.
   - Antes de producir el frente público, filtrar explícitamente las soluciones con constraint satisfecho. Si no hay ninguna viable, el frente factible será vacío.
   - Es aceptable que NSGA-III conserve temporalmente individuos inviables cuando no haya suficientes viables en la población; no pueden aparecer en el frente final factible.

2. `SeededBinaryTournamentSelection`
   - Mantener selection/ranking existente, pero asegurar que los ranks que compara proceden del ranking constraint-aware configurado en NSGA-III.

### Cálculo y export de `is_pareto`

1. `api.serialization._non_dominated_evaluation_ids()`
   - Corregir el defecto actual: debe ejecutar ranking real y constraint-aware sobre las soluciones del snapshot, no devolver todos sus IDs.
   - Conviene renombrarlo a `_feasible_non_dominated_evaluation_ids()` para que la semántica quede clara.

2. `api.serialization._serialize_solution()`
   - `is_pareto` será verdadero solo si `is_feasible` es verdadero y el ID está en el conjunto Pareto.

3. `api.manager_runtime.execute_job()`
   - Usar el mismo helper tanto para el resultado final como para cada snapshot.
   - `pareto_solutions`, `pareto_evaluation_ids` y counts se construirán desde el conjunto viable.

4. `process_miner.OptimizedProcessMiner.get_non_dominated_*()`
   - Conservar los accessors, pero garantizar que `self.non_dominated` ya es el frente factible.

5. `job_store.JobStore`
   - Seguir filtrando por `is_pareto`, ahora persistido de forma coherente; para datos v2 puede reforzarse el query con `is_feasible = true`.

6. `model_selection.select_weighted_model()`
   - Excluir candidatos con `is_feasible is False`, incluso con `scope="all"`, para impedir que la selección final ASF elija un modelo inviable. Los registros legacy sin el campo siguen siendo elegibles por compatibilidad.

### Test sintético obligatorio

En `test_optimizer.py` se construirán dos `FloatSolution` con la convención interna de minimización:

```text
A viable:    objectives = [-0.8, -0.8, -0.8, -0.8], constraint =  0.0
B inviable:  objectives = [-1.0, -1.0, -1.0, -1.0], constraint = -1.0
```

El resultado esperado es un frente factible que contiene A y nunca B. El mismo caso se cubrirá en serialización final y snapshot.

Tests existentes a ampliar:

- `test_optimizer_runs_and_returns_non_dominated()`;
- `test_optimizer_captures_generation_snapshots()`;
- `test_process_miner.test_non_dominated_accessors()`;
- `test_api.test_serialize_solution_includes_evaluation_error()`;
- tests de scope Pareto de `test_api.py` y `test_job_store.py`;
- `test_model_selection.py` para confirmar que ASF ignora inviables.

## P1.1 — Auditoría del log recibido por cada métrica

### Flujo verificado

En `PromPipelineEvaluator.evaluate()`:

1. `LogLoader.loadForExperiment()` devuelve `log`, el XLog original cacheado por experimento/path.
2. `PreprocessingPipeline.apply(context, log, request)` produce `processedLog`.
3. `discoverModel(context, processedLog, request)` entrega exclusivamente `processedLog` al miner seleccionado.
4. `ConformanceMetricsCalculator.compute(context, log, ...)` recibe `log`, no `processedLog`.
5. Un único `ConformanceComputation` encapsula ese log original para todas las métricas pedidas.

### Matriz exacta

| Métrica | Clase/método | Log usado |
|---|---|---|
| fitness, alignment | `Fitness.compute()` -> `ConformanceComputation.getFitness()` -> `getReplayResult()` | `ConformanceComputation.log`, creado con el `log` original |
| fitness, replay | `getReplayFitnessLikePm4py()` -> `getReplayResult()` | original |
| fitness, replay-token | `getTokenReplayResult()` -> `TokenReplayComputation(log, ...)` | original |
| precision, alignment | `Precision.compute()` -> `getAlignment()`; consume replay construido con el original | original indirectamente mediante replay/mapping |
| precision, replay | `getReplayPrecision()` -> `ETCAlgorithm.exec(context, log, ...)` | original directamente |
| precision, replay-token | `TokenReplayPrecisionComputation(log, ...)` | original directamente |
| generalisation, alignment | `Generalisation.compute()` -> `getAlignment()` | original mediante el replay |
| generalisation, replay | `getReplayGeneralisation()` recorre `getReplayResult()` | original mediante el replay |
| generalisation, replay-token | activaciones de `getTokenReplayResult()` | original mediante token replay |
| simplicity | `Simplicity.compute()` -> `computeStructuralSimplicity(net)` | ninguno; solo net |

Las demás métricas del catálogo (`places`, `transitions`, `arcs`, `t_edges`, `cycl_complx`, `cfc`, `elc`, `ratio`, `joins`, `splits`) son estructurales y usan `ConformanceComputation.getNet()`, no un XLog.

### Resultado P1

No se planifica cambiar el routing de producción: la separación `processedLog` para discovery / `log` original para evaluation ya existe y es uniforme para todos los miners.

Hay un riesgo de aliasing que merece una prueba: `PreprocessingPipeline` empieza con `current = sourceLog`, y algunos wrappers entregan ese objeto a librerías ProM de terceros. No hay en el código propio una mutación intencional del original, pero tampoco una barrera defensiva común.

Antes de cerrar P1 se añadirá en `PreprocessingPipelineTest` una comprobación de que cada filtro deja intactos traces/events/classifiers del source log. Solo si falla se cambiará `PromPipelineEvaluator`/`PreprocessingPipeline` para aplicar preprocessing sobre un clon. Esto respeta la instrucción de no cambiar el flujo si ya funciona como se pretende.

Tests reutilizables:

- `TokenReplayComputationTest` para fitness/precision/generalisation con un log explícito;
- `SimplicityMetricTest` para probar que simplicity funciona con `log == null`;
- `ConformanceStructuralMetricsTest` para el resto de métricas model-only;
- `PromPipelineEvaluatorRealTest` y `PreprocessingPipelineTest` para la separación discovery/evaluation.

## P2.1 — Seed y reproducibilidad

### Propagación actual

```text
RunPage.seed (opcional)
  -> OptimizationJobManager._normalize_seed
       si falta: secrets.randbits(32)
  -> job.request.discover.seed
  -> manager_runtime.execute_job
  -> OptimizedProcessMiner(seed)
       self.rng = random.Random(seed)
  -> PipelineOptimizationProblem(rng=self.rng)
       create_solution(): rng.uniform
  -> PipelineNSGAIIIOptimizer(rng=self.rng)
       SeededBinaryTournamentSelection
       SeededSBXCrossover
       SeededPolynomialMutation
```

La misma instancia `random.Random` se comparte deliberadamente entre creación, selection, crossover y mutation. `PipelineSearchSpace.decode()` es determinista. `UniformReferenceDirectionFactory` no introduce una elección aleatoria visible en este código.

### Fuentes no cubiertas por la seed

- `ProMServiceClient.evaluate_pipeline()` no envía seed en `PipelineRequest`.
- Ningún `*MinerDiscoverer` recibe o configura una seed explícita.
- `InductiveMinerDiscoverer` fija `use_multithreading` desde el pipeline y su valor por defecto no optimizable es `true`.
- `ThreadPoolEvaluator` ejecuta candidatos concurrentemente cuando `n_workers > 1`. `as_completed()` observa orden de terminación, aunque devuelve la lista de soluciones en el orden original.
- `PipelineOptimizationProblem.evaluation_cache` se consulta/escribe desde varios threads sin un lock específico; dos candidatos iguales pueden evaluarse a la vez.
- `LogLoader` comparte el mismo XLog cacheado entre evaluaciones del experimento; los preprocessors/miners de terceros pueden ser otra fuente de estado concurrente.
- Spark/ProM y las librerías de miners pueden usar threads, RNGs o estado global interno no controlado.
- La opción textual `Hybrid ILP / discovery_strategy = Random` no recibe seed; además, el mapper actual no tiene un caso `Random` y cae en `DiscoveryStrategyType.CAUSAL`, por lo que el nombre no prueba por sí mismo aleatoriedad en la ejecución actual.
- La elección del primer final marking desde el `Set<Marking>` de un APN puede depender del orden de iteración. P0.1 debe capturar una vez el marking usado; para reproducibilidad futura conviene también estabilizar el orden serializado sin cambiar la semántica del miner.

### Acción P2 acordada

No se rediseñará RNG ni se exigirá reproducibilidad bit a bit. Se mantendrá el test existente `test_seeded_optimizer_reproduces_final_population()` y se añadirá, como diagnóstico no bloqueante, una ejecución repetida con `n_workers > 1` usando evaluator determinista.

El resultado documentado será: la seed reproduce el componente evolutivo Python bajo evaluator determinista, pero no controla los miners Java. Los nuevos lotes experimentales deben usar seeds maestras distintas para runs independientes.

## Mapa consolidado de archivos

### Java: cambios previstos

- `evaluation/discovery/DiscoveryArtifactFactory.java`: eliminar inferencia, resolver accepting semantics reales.
- `evaluation/discovery/DiscoveryArtifact.java`: final evaluado explícito y lista completa.
- `evaluation/serialization/PetriNetSemanticsSerializer.java`: nuevo serializer/test point.
- `evaluation/PromPipelineEvaluator.java`: ensamblar semántica, contar visibles y emitir factibilidad.
- `api/dto/EvaluationResult.java`: metadata interna de evaluación.
- `api/dto/PipelineResponse.java`: respuesta HTTP inmediata.
- `api/dto/ArtifactBulkResponse.java`: transitions/markings/factibilidad/version.
- `artifacts/StoredArtifactMetadata.java`: metadata temporal completa.
- `artifacts/ArtifactStore.java`: round-trip de metadata.
- `app/http/PromHttpHandlers.java`: mapear el DTO ampliado.
- `app/http/OpenApiDocs.java`: contrato OpenAPI.
- Los seis `evaluation/discovery/miners/*Discoverer.java`: verificar contrato de salida; cambiar solo el adapter que no exponga semántica real.
- `evaluation/conformance/ConformanceMetricsCalculator.java` y `ConformanceComputation.java`: no requieren cambio funcional P1; sirven como puntos de verificación.
- `evaluation/preprocessing/PreprocessingPipeline.java`: sin cambio previsto, salvo que falle el test de inmutabilidad del log original.

### Python: cambios previstos

- `java_service_client.py`: transportar factibilidad/version.
- `problem.py`: declarar y poblar el hard constraint; cache completa.
- `optimizer.py`: comparator y frente factible constraint-aware.
- `process_miner.py`: accessors del frente ya filtrado.
- `api/serialization.py`: `is_pareto` correcto, ranking de snapshots, CSV y metadata.
- `api/manager_runtime.py`: conjuntos Pareto final/snapshots y counts.
- `api/manager_persistence.py`: fuente semántica v2 autoritativa.
- `api/petri.py`: consumo de `invisible`/`final_marking`; inferencia solo legacy.
- `api/petri_routes.py`: aceptar el marking singular canónico.
- `job_store.py`: columnas, migraciones, queries y serialización.
- `api/openapi.py`: esquema público.
- `model_selection.py`: impedir selección ASF de inviables.

### Frontend: cambios previstos

- `components/PnmlViewer.jsx`: `invisible` canónico con fallback legacy.
- `pages/ResultsPage.jsx`: mapear factibilidad y `final_marking`, y enviarlo al renderer.
- No es necesario cambiar `ParetoFrontScatter.jsx`: recibe ya la colección filtrada por `is_pareto`.

## Tests existentes reutilizables

| Archivo | Reutilización |
|---|---|
| `ArtifactStoreTest.java` | round-trip de metadata semántica Java |
| `PromPipelineEvaluatorRealTest.java` | validación por familia de miner |
| `TokenReplayComputationTest.java` | markings e invisibilidad reales |
| `SimplicityMetricTest.java` | simplicity model-only |
| `ConformanceStructuralMetricsTest.java` | métricas estructurales model-only |
| `PreprocessingPipelineTest.java` | inmutabilidad del log original |
| `OpenApiDocsTest.java` | campos requeridos del contrato Java |
| `PromHttpHandlersTest.java` | respuesta `/pipeline` ampliada |
| `test_petri_serialization.py` | contrato v2 y compatibilidad legacy |
| `test_manager_persistence.py` | prioridad del artifact sobre PNML |
| `test_job_store.py` | migración, DB y lectura API |
| `test_java_service_client.py` | transporte Java -> Python |
| `test_problem.py` | constraint, atributos y caché |
| `test_optimizer.py` | dominancia factible y reproducibilidad Python |
| `test_process_miner.py` | accessors del frente factible |
| `test_api.py` | serialización pública y scopes |
| `test_model_selection.py` | ASF no selecciona inviables |

## Orden de implementación

1. Crear serializer semántico Java y tests unitarios.
2. Eliminar fallbacks topológicos de `DiscoveryArtifactFactory`; validar todos los miners con el test real.
3. Ampliar artifacts/respuesta Java con contrato v2, transitions, markings y factibilidad.
4. Propagar metadata por `ProMServiceClient` y convertir `PipelineOptimizationProblem` en problema con un constraint.
5. Hacer NSGA-III, frente final y snapshots constraint-aware; añadir el test sintético obligatorio.
6. Persistir/exponer el contrato v2 en DB, API y CSV; mantener lector legacy aislado.
7. Adaptar renderer/frontend al nombre `invisible` y `final_marking`.
8. Ejecutar auditoría P1 con test de inmutabilidad; no cambiar routing si pasa.
9. Ejecutar y documentar diagnósticos P2 sin bloquear el release.

## Definition of done

- Todo artifact nuevo tiene `model_schema_version: 2`, markings reales y `invisible` boolean explícito.
- El `final_marking` exportado es el mismo objeto semántico usado por la evaluación.
- No existe source/sink ni label inference en el camino v2.
- Cero transitions y tau-only producen `NO_VISIBLE_TRANSITIONS` y constraint negativo.
- Una net con al menos una transition visible sigue el flujo normal.
- Objetivos reales y factibilidad permanecen separados.
- NSGA-III usa dominancia con constraints y el frente público filtra inviables.
- `is_pareto` final y de snapshots es consistente con factibilidad y ranking real.
- Fitness, precision y generalisation siguen usando el log original; simplicity y las métricas estructurales no reciben log.
- Pasan suites Java/Python, build frontend y test real por miner.
- No se introduce rechazo por conectividad, soundness, deduplicación, isomorfismo, weighted arcs ni cambios en `pareto_front_analysis`.

## Fuera de alcance confirmado

No se tocarán en esta fase: deduplicación estructural, fingerprints canónicos, diversidad de población, conectividad como constraint, soundness como constraint/penalty, selección final metodológica, process families, variation points ni el repositorio externo de análisis Pareto.
