# Split Miner source patch — minersweeper-split-v2

Minersweeper compiles five vendored classes into the service artifact. The original
`prom:SplitMiner:1.7.1` dependency supplies the remaining classes and the unchanged
BPMN→Petri converter. Service classes precede dependencies in the supported
launchers. A runtime origin check rejects a mixed or unpatched implementation.

Base source: [iharsuvorau/split-miner, commit 3060b3f1277d444caeea0f7fff4d27d2d53c6335](https://github.com/iharsuvorau/split-miner/tree/3060b3f1277d444caeea0f7fff4d27d2d53c6335).
`upstream.json` records original source hashes. Original instruction bytecode for
SplitMiner, Oracle and GatewayMap was checked against the installed slim JAR.
Copyright belongs to the Apromore Initiative and original contributors;
headers are retained, with LGPL v3 and GPL v3 texts provided here.

Vendored files under `src/main/java`:

- `processmining/splitminer/oracle/Oracle.java`: stable structural tie ordering;
  identity collections preserve candidates even if their signatures coincide.
- `processmining/splitminer/oracle/OracleItem.java`: consistent equality/hash;
  ordered structural hierarchy keys and identity-preserving child collections.
- `processmining/splitminer/SplitMiner.java`: ordered branch construction;
  ordered bottom-up RPST decisions over the original BPMN flows; bonds/rigids
  recover internal real flows omitted by RPST normalization; polygons retain
  their own branch. Vertex identity is fixed before graph insertion; inner joins
  are ordered structurally. Cancellation/reproducibility failures propagate;
  explicit fallback route.
- `processmining/splitminer/dfgp/DirectlyFollowGraphPlus.java`: ordered adjacency
  snapshots for both maximum-capacity witness traversals, with strict capacity
  improvements and stable first-witness ties; ordered BPMN construction.
- `bpmn/helper/GatewayMap.java`: monotone AND→XOR closure using affected-node
  queue, then a snapshot repair plan applied simultaneously.

The service's `BpmnStructuralOrder` orders join decisions and multiple repairs by topology and
activity semantics rather than UUIDs or gateway names. A logical ordering limit
fails explicitly instead of choosing arbitrary IDs. This fork is therefore an
integrated service variant, not a standalone replacement JAR for arbitrary ProM
installations.

Changes to these policies require bumping `SplitMiner.determinismPolicyVersion()`.
Do not remove the vendored classes without changing discovery/metadata/tests.
