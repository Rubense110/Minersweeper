# MineSweeper Rework — Model Semantics, Feasibility and Pareto Consistency

## 1. Purpose

This document defines the **immediate rework required in MineSweeper before continuing with the downstream Pareto-front analysis and process-variability work**.

The current experiments are useful, but the exported process models do not yet contain all the semantic information required to analyze them reliably. In addition, degenerate models with no observable process behavior are currently able to participate as feasible multi-objective solutions.

The goal of this rework is deliberately narrow:

1. Export the complete semantic information of each generated Accepting Petri Net that downstream analysis needs.
2. Prevent models with no observable transitions from being treated as feasible solutions.
3. Ensure Pareto membership is computed consistently with that feasibility condition.
4. Verify, without redesigning the methodology, that candidate models are evaluated against the original event log.
5. Perform a low-priority review of seed propagation and reproducibility.

This document **does not define the later rework of the external `pareto_front_analysis` code**. Deduplication, graph isomorphism, disconnected-model analysis, soundness diagnostics and variability modeling will be addressed separately after MineSweeper produces the required data correctly.

---

# 2. Current experiment context

MineSweeper performs multi-objective process discovery and returns process models evaluated with several quality dimensions, including:

- fitness;
- precision;
- generalisation;
- simplicity.

Different individuals may use different preprocessing/discovery pipelines, but the discovered models are intended to be evaluated against the **same original event log**.

The current exported model representation contains, at least:

- places;
- transitions;
- arcs;
- quality metrics;
- pipeline/algorithm information;
- solution metadata.

However, the current export does **not explicitly contain**:

- the initial marking;
- the final marking;
- whether each transition is invisible/silent.

These properties must no longer be reconstructed heuristically in downstream analysis.

The experiments also contain models with no observable process behavior. Some of these can receive extreme objective values such as very high simplicity, precision or generalisation, and can therefore remain nondominated even though they are not meaningful final process models.

---

# 3. Scope of this rework

## 3.1 Required changes

The following changes are part of this rework:

1. Export the real initial marking.
2. Export the real final marking.
3. Export an explicit `invisible` property for every transition.
4. Treat any model with zero visible transitions as infeasible.
5. Ensure infeasible models do not belong to the feasible Pareto front.
6. Verify that all model-quality metrics are evaluated against the original event log.
7. Review seed propagation and possible nondeterminism at low priority.

## 3.2 Explicitly out of scope

Do **not** implement the following as part of this rework:

- structural deduplication;
- Petri-net graph isomorphism;
- canonical fingerprints for downstream equality;
- duplicate-removal strategies inside the evolutionary population;
- population diversity mechanisms based on structural equivalence;
- filtering disconnected models;
- repairing disconnected models;
- soundness as a hard feasibility constraint;
- soundness-based penalties;
- transition-vs-activity semantic aggregation;
- process-family construction;
- variation-point discovery;
- Provop or any other process-variability approach;
- domain-expert questionnaires;
- final model ranking/selection;
- changes to the external `pareto_front_analysis` code;
- redesign of the RNG architecture unless a clear bug is found.

These topics belong to a later phase.

---

# 4. Export initial and final markings

## 4.1 Requirement

Every exported process model must include the **actual initial marking and final marking used by MineSweeper**.

They must come directly from the internal Accepting Petri Net representation or the data structure used during model evaluation.

They must **not** be inferred from:

- places with indegree zero;
- places with outdegree zero;
- naming conventions;
- ordering of places;
- fallback assumptions.

## 4.2 Representation

The export must preserve token multiplicity.

Recommended representation:

```json
{
  "initial_marking": {
    "p0": 1
  },
  "final_marking": {
    "p8": 1
  }
}
```

A marking involving more than one place must also be representable:

```json
{
  "initial_marking": {
    "p0": 1,
    "p1": 1
  },
  "final_marking": {
    "p8": 1,
    "p9": 1
  }
}
```

Even if the current experiments normally use one token in one place, the export should reflect the real marking rather than encode an unnecessary assumption.

## 4.3 Important constraint

The IDs used in `initial_marking` and `final_marking` must correspond exactly to place IDs in the exported `places` collection.

Example invariant:

```text
set(initial_marking.keys()) ⊆ set(place_ids)
set(final_marking.keys())   ⊆ set(place_ids)
```

## 4.4 Acceptance tests

For each exported model:

- every initial-marking place exists in the model;
- every final-marking place exists in the model;
- token counts are positive integers;
- serializing and deserializing the model preserves both markings exactly;
- the exported markings match the markings passed to the process-quality evaluation.

---

# 5. Export transition invisibility explicitly

## 5.1 Requirement

Every transition must include an explicit boolean field:

```json
{
  "id": "t4",
  "label": "IV Antibiotics",
  "invisible": false
}
```

Silent transition example:

```json
{
  "id": "t7",
  "label": "",
  "invisible": true
}
```

The exact label of an invisible transition is not considered semantically relevant for the current downstream work.

A transition may therefore have labels such as:

```text
""
"tau"
"tau from tree"
"silent"
```

but downstream code must rely on:

```text
invisible == true
```

rather than the label.

## 5.2 Do not infer invisibility from labels

The exported `invisible` value must be obtained from MineSweeper's actual internal Petri-net representation.

Do not implement logic such as:

```python
label == ""
label.startswith("tau")
regex(...)
```

as the source of truth.

## 5.3 Acceptance tests

For every transition:

- `invisible` is present;
- `invisible` is a boolean;
- visible transitions preserve their real activity label;
- silent transitions are correctly marked regardless of their textual label;
- model serialization/deserialization preserves the flag.

---

# 6. Arcs

No weighted-arc rework is required.

MineSweeper does not currently model weighted Petri nets, and introducing a synthetic field such as:

```json
"weight": 1
```

would add no useful information.

Each arc should continue to be exported explicitly using its own identity, source and target, for example:

```json
{
  "id": "a17",
  "source": "p3",
  "target": "t4"
}
```

If the internal model allows multiple distinct arcs involving the same source and target, they should remain represented as distinct arcs. Do **not** collapse them into one artificial weighted arc.

No additional arc semantics are required in this rework.

---

# 7. Feasibility constraint for degenerate models

## 7.1 New hard constraint

A generated model is infeasible when:

```text
n_visible_transitions == 0
```

where:

```text
visible transition := transition with invisible == false
```

This rule covers both:

### Completely transition-free model

```text
places > 0
transitions = 0
```

and:

### Tau-only model

```text
p0 -> tau -> p1 -> tau -> p2
```

A model containing no observable activity does not represent a useful candidate process model for the later selection task.

## 7.2 This must be treated as feasibility, not as an objective

Do **not** solve this by assigning arbitrary values such as:

```text
fitness = 0
precision = 0
simplicity = 0
generalisation = 0
```

The correct semantics are:

```text
candidate violates feasibility constraint
```

The optimization layer should distinguish:

```text
feasible candidate
```

from:

```text
infeasible candidate
```

## 7.3 Expected behavior

Conceptually:

```text
discover candidate
      |
      v
count visible transitions
      |
      +-- 0 --> infeasible
      |
      +-- >0 --> normal evaluation / optimization flow
```

The exact integration point should follow the current MineSweeper optimizer architecture.

Codex should inspect the code before deciding whether the check belongs:

- immediately after process discovery;
- in a candidate-validation stage;
- in the objective/constraint interface;
- or in the optimizer's constraint handling.

The semantic requirement is fixed even if the best implementation location depends on the codebase.

## 7.4 Diagnostics

It is acceptable and useful to retain infeasible candidates in diagnostic/history outputs when the architecture already stores all evaluated candidates.

However:

> An infeasible zero-visible-transition model must never be presented as a feasible Pareto-optimal solution.

Recommended metadata if compatible with the current architecture:

```json
{
  "is_feasible": false,
  "constraint_violations": [
    "NO_VISIBLE_TRANSITIONS"
  ]
}
```

Do not introduce a large new constraint framework solely for this field if MineSweeper already has another standard mechanism for representing feasibility.

---

# 8. Pareto-front consistency

## 8.1 Requirement

Pareto membership must be computed over the **feasible candidate set**.

Formally, if:

```text
F = {x | x satisfies all hard constraints}
```

then Pareto dominance for the final feasible front must operate on:

```text
x ∈ F
```

Models satisfying:

```text
n_visible_transitions == 0
```

must not appear in the feasible Pareto front.

## 8.2 Required review

Inspect the current code path responsible for:

- constraint handling;
- objective-vector generation;
- nondominated sorting;
- `is_pareto`;
- snapshot export.

Confirm that introducing the new feasibility rule cannot leave an infeasible candidate marked as a normal feasible Pareto solution.

## 8.3 Pareto validation test

Add or run at least one automated test with synthetic objective vectors.

Example:

```text
A = feasible,   objectives = [0.8, 0.8, 0.8, 0.8]
B = infeasible, objectives = [1.0, 1.0, 1.0, 1.0]
```

Expected result:

```text
B must not displace A from the feasible Pareto front.
```

The specific sign convention used internally by MineSweeper must be respected.

---

# 9. Metric-evaluation audit

## 9.1 Current intended behavior

The intended methodology is:

```text
original event log L
        |
        +--> preprocessing/discovery pipeline 1 --> M1
        |
        +--> preprocessing/discovery pipeline 2 --> M2
        |
        +--> preprocessing/discovery pipeline 3 --> M3

M1 evaluated against L
M2 evaluated against L
M3 evaluated against L
```

The preprocessing pipeline may alter the log used for **discovery**, but it must not change the reference log used to compare the final candidate models.

This is already believed to be the current MineSweeper behavior.

## 9.2 Task

Codex must trace the code and verify that all relevant quality metrics use the same original event log:

- fitness;
- precision;
- generalisation;
- simplicity where applicable to the model only.

For metrics that are structurally model-only, simply document that no event log is involved.

## 9.3 What to inspect

Trace:

1. where the original log is loaded;
2. where preprocessing creates transformed logs;
3. where each miner receives its discovery log;
4. where each metric function receives its log;
5. whether any branch accidentally uses the transformed/discovery log for final model evaluation.

## 9.4 Expected outcome

If all evaluation paths already use the original log:

> Do not change the implementation.

Document the verified call/data flow.

If any evaluation path uses a preprocessed log:

> Report it before making a methodological change unless it is clearly an implementation bug contradicting the existing design.

The default requirement is that final cross-candidate model evaluation uses the original log.

---

# 10. Disconnected models

No filtering rule based solely on graph connectivity is to be introduced in MineSweeper during this rework.

Current experiments contain models with more than one weakly connected component.

Do not implement:

```text
components > 1 -> infeasible
```

at this stage.

Once initial and final markings are exported correctly, the downstream analysis will investigate:

- reachability from the initial marking;
- ability to contribute to the final marking;
- dead/unreachable components;
- legitimate concurrent structure;
- behavioral anomalies.

Therefore:

> MineSweeper must preserve and export disconnected models normally unless they violate another already-defined hard constraint.

---

# 11. Soundness

Soundness is **not** a hard feasibility requirement in this rework.

Do not reject or penalize a model solely because it is not sound.

Reasons:

- several supported discovery algorithms do not guarantee sound models;
- rejecting all unsound models could introduce strong miner-dependent bias;
- it has not yet been established that classical workflow-net soundness is required for the eventual model-selection use case.

Later analysis may compute:

- soundness;
- deadlocks;
- dead transitions;
- proper completion;
- reachability properties;

but these will initially be diagnostic variables.

No MineSweeper behavior should change based on soundness at this stage.

---

# 12. Duplicate models

Duplicate handling inside MineSweeper is explicitly out of scope.

The current optimizer may retain several structurally equivalent models in the population.

Do not currently implement:

- structural duplicate rejection;
- isomorphism checks inside evolution;
- duplicate penalties;
- replacement of duplicate individuals;
- diversity bonuses;
- structural niching.

The downstream analysis will later deduplicate models using exact Petri-net isomorphism.

The possible loss of population diversity caused by duplicate individuals is worth studying later, but it must not be mixed into this rework because it would change the evolutionary dynamics of MineSweeper.

---

# 13. Seed and reproducibility review

This task is secondary and must not block the main rework.

Some previous experimental batches accidentally reused the same master seeds while producing non-identical results.

Possible causes include:

- multi-threading;
- multi-processing;
- miner-internal randomness;
- independent RNG instances;
- NumPy/Python RNG separation;
- worker completion order;
- external libraries.

## 13.1 Required task

Inspect and document:

- where the master seed enters MineSweeper;
- which RNG implementations are initialized from it;
- how worker processes/threads obtain seeds;
- whether miners receive explicit seeds;
- whether any obvious RNG source is unseeded;
- whether multithreading can reasonably explain nondeterministic execution.

## 13.2 Do not overengineer

Do not redesign the RNG architecture during this rework unless an obvious implementation bug is found.

Do not make bit-for-bit reproducibility under multithreading a release requirement.

Future experimental batches should simply use distinct master seeds for distinct independent runs.

---

# 14. Backward compatibility

If old result files need to remain loadable, backward compatibility may be provided.

However, new exports must contain:

```text
initial_marking
final_marking
transition.invisible
```

Downstream inference of these fields must not remain the default for newly generated results.

If an export/version field already exists, consider incrementing it.

If none exists, Codex should assess whether introducing a lightweight schema/version identifier is worthwhile. Do not introduce a large serialization redesign solely for this rework.

---

# 15. Expected exported model semantics

After the rework, a solution should provide enough information to reconstruct the Accepting Petri Net without guessing its semantics.

Illustrative structure:

```json
{
  "places": [
    {"id": "p0"},
    {"id": "p1"},
    {"id": "p2"}
  ],
  "transitions": [
    {
      "id": "t0",
      "label": "Register request",
      "invisible": false
    },
    {
      "id": "t1",
      "label": "",
      "invisible": true
    }
  ],
  "arcs": [
    {
      "id": "a0",
      "source": "p0",
      "target": "t0"
    },
    {
      "id": "a1",
      "source": "t0",
      "target": "p1"
    },
    {
      "id": "a2",
      "source": "p1",
      "target": "t1"
    },
    {
      "id": "a3",
      "source": "t1",
      "target": "p2"
    }
  ],
  "initial_marking": {
    "p0": 1
  },
  "final_marking": {
    "p2": 1
  }
}
```

The exact surrounding JSON/CSV serialization may follow the current MineSweeper output format. A full output-format redesign is not required.

---

# 16. Implementation order

Use the following priority order.

## P0 — Required before new experiments

### P0.1 — Export real markings

Implement and test:

```text
initial_marking
final_marking
```

### P0.2 — Export explicit transition invisibility

Implement and test:

```text
transition.invisible
```

### P0.3 — Zero-visible-transition feasibility constraint

Implement:

```text
n_visible_transitions == 0 -> infeasible
```

### P0.4 — Pareto consistency

Ensure infeasible candidates cannot appear in the feasible Pareto front.

---

## P1 — Required verification

### P1.1 — Metric evaluation

Verify that all candidate models are evaluated against the original event log.

Change code only if the implementation contradicts that intended behavior.

---

## P2 — Secondary review

### P2.1 — Seed propagation

Inspect and document current RNG/seed handling.

Do not delay P0/P1 work for this task.

---

# 17. Acceptance checklist

The rework is considered complete when all of the following hold.

## Export

- [ ] Every newly exported model contains its real initial marking.
- [ ] Every newly exported model contains its real final marking.
- [ ] Markings preserve token multiplicity.
- [ ] Marking place IDs reference valid exported places.
- [ ] Every transition contains an explicit boolean `invisible`.
- [ ] No downstream inference is required to reconstruct these semantics.

## Feasibility

- [ ] A model with zero transitions is infeasible.
- [ ] A model containing only invisible transitions is infeasible.
- [ ] A model with at least one visible transition remains eligible for normal evaluation.
- [ ] The feasibility rule is expressed as a constraint, not by fabricating objective values.

## Pareto

- [ ] An infeasible model cannot appear as a normal feasible Pareto solution.
- [ ] `is_pareto` or equivalent exported status is consistent with feasibility.
- [ ] At least one synthetic test validates infeasible-vs-feasible Pareto behavior.

## Metrics

- [ ] Fitness uses the original reference log.
- [ ] Precision uses the original reference log.
- [ ] Generalisation uses the original reference log.
- [ ] Structurally defined metrics are documented as model-only where appropriate.
- [ ] Discovery preprocessing does not silently replace the reference log used for final candidate comparison.

## Non-goals

- [ ] No connectivity-based rejection was introduced.
- [ ] No soundness-based rejection was introduced.
- [ ] No structural deduplication was introduced into the evolutionary algorithm.
- [ ] No variation-analysis code was mixed into MineSweeper.

## Secondary

- [ ] Seed propagation was reviewed or explicitly left documented as pending.
- [ ] No unnecessary RNG redesign was performed.

---

# 18. Suggested first Codex task

Before modifying code, inspect the repository and produce a concrete implementation map.

Suggested prompt:

> Read this document and inspect the MineSweeper codebase. Do not modify files yet. Identify:
> 1. the internal representation of the Petri net and accepting markings;
> 2. the result serialization/export path;
> 3. how transition invisibility is represented internally;
> 4. where candidate feasibility/constraints should be enforced;
> 5. where nondominated sorting / Pareto status is computed;
> 6. where fitness, precision, generalisation and simplicity are calculated and which event-log object each receives;
> 7. how the master seed propagates into workers, optimizers and miners.
>
> Return a file-by-file implementation plan with the exact classes/functions that should change, the minimum required changes, and tests to add. Do not implement anything until the plan has been reviewed.

---

# 19. What happens after this rework

Once MineSweeper has been updated and a new experiment has been generated, the next phase will concern the **external analysis pipeline**, not MineSweeper itself.

That later phase is expected to address:

- exact isomorphism-based model deduplication;
- preservation of duplicate occurrences/provenance;
- validation that isomorphic Accepting Petri Nets have identical quality metrics;
- analysis of disconnected models using the exported markings;
- soundness and reachability as diagnostics;
- separation of transition identity from domain activity labels;
- correction of duplicated/redundant structural features;
- recalculation/validation of the Pareto set over unique, feasible models;
- process-family construction;
- automatic variation-point discovery;
- domain-guided selection of a final Pareto-optimal process model.

None of these tasks should be prematurely introduced into the current MineSweeper rework.
