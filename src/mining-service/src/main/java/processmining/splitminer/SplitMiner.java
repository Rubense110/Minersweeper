/*
 * Copyright © 2009-2018 The Apromore Initiative.
 *
 * This file is part of "Apromore".
 *
 * "Apromore" is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as
 * published by the Free Software Foundation; either version 3 of the
 * License, or (at your option) any later version.
 *
 * "Apromore" is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty
 * of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this program.
 * If not, see <http://www.gnu.org/licenses/lgpl-3.0.html>.
 */

// Modified for Minersweeper: ordered splits/joins, original-flow RPST projection and explicit execution failures.
package processmining.splitminer;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import com.minersweeper.javaservice.evaluation.ReproducibilityException;
import com.minersweeper.javaservice.evaluation.reproducibility.BpmnStructuralOrder;
import java.util.concurrent.CancellationException;

import bpmn.helper.DiagramHandler;
import bpmn.helper.GatewayMap;
import bpmn.structuring.StructuringService;
import de.hpi.bpt.graph.DirectedEdge;
import de.hpi.bpt.graph.DirectedGraph;
import de.hpi.bpt.graph.abs.IDirectedGraph;
import de.hpi.bpt.graph.algo.rpst.RPST;
import de.hpi.bpt.graph.algo.rpst.RPSTNode;
import de.hpi.bpt.graph.algo.tctree.TCType;
import de.hpi.bpt.hypergraph.abs.Vertex;
import java.util.*;
import org.deckfour.xes.classification.XEventClassifier;
import org.deckfour.xes.model.XLog;
import org.processmining.models.graphbased.directed.bpmn.BPMNDiagram;
import org.processmining.models.graphbased.directed.bpmn.BPMNDiagramImpl;
import org.processmining.models.graphbased.directed.bpmn.BPMNEdge;
import org.processmining.models.graphbased.directed.bpmn.BPMNNode;
import org.processmining.models.graphbased.directed.bpmn.elements.*;
import processmining.log.LogParser;
import processmining.log.SimpleLog;
import processmining.optimization.SimpleDirectlyFollowGraph;
import processmining.splitminer.dfgp.DirectlyFollowGraphPlus;
import processmining.splitminer.oracle.Oracle;
import processmining.splitminer.oracle.OracleItem;
import processmining.splitminer.ui.dfgp.DFGPUIResult;
import processmining.splitminer.ui.miner.SplitMinerUIResult;

/** Created by Adriano on 24/10/2016. */
public class SplitMiner {
  private String discoveryRoute = "standard";
  public static String determinismPolicyVersion() { return "minersweeper-split-v2"; }
  public String getDiscoveryRoute() { return discoveryRoute; }
  private static void propagateExecutionFailure(Exception error) {
    if (error instanceof ReproducibilityException) throw (ReproducibilityException)error;
    if (error instanceof ExecutionChecks.WorkLimitExceeded) throw (ExecutionChecks.WorkLimitExceeded)error;
    if (error instanceof CancellationException) throw (CancellationException)error;
    ExecutionChecks.check();
  }


  private SimpleLog log;
  private DirectlyFollowGraphPlus dfgp;
  private BPMNDiagram bpmnDiagram;

  private boolean replaceIORs;
  private boolean removeLoopActivities;
  private SplitMinerUIResult.StructuringTime structuringTime;

  private int gateCounter;
  private HashMap<String, Gateway> candidateJoins;

  private Set<Gateway> bondsEntries;
  private Set<Gateway> rigidsEntries;

  public SplitMiner() {
    this.replaceIORs = true;
    this.removeLoopActivities = true;
    this.structuringTime = SplitMinerUIResult.StructuringTime.NONE;
  }

  public SplitMiner(boolean replaceIORs, boolean removeLoopActivities) {
    this.replaceIORs = replaceIORs;
    this.removeLoopActivities = removeLoopActivities;
    this.structuringTime = SplitMinerUIResult.StructuringTime.NONE;
  }

  public BPMNDiagram getBPMNDiagram() {
    return bpmnDiagram;
  }

  public BPMNDiagram mineBPMNModel(
      XLog log,
      XEventClassifier xEventClassifier,
      double percentileFrequencyThreshold,
      double parallelismsThreshold,
      DFGPUIResult.FilterType filterType,
      boolean parallelismsFirst,
      boolean replaceIORs,
      boolean removeLoopActivities,
      SplitMinerUIResult.StructuringTime structuringTime) {
    discoveryRoute = "standard";
    ExecutionChecks.check();
    this.replaceIORs = replaceIORs;
    this.removeLoopActivities = removeLoopActivities;
    this.structuringTime = structuringTime;

    this.log = (new LogParser()).getSimpleLog(log, xEventClassifier, 1.00);

    generateDFGP(
        percentileFrequencyThreshold, parallelismsThreshold, filterType, parallelismsFirst);
    try {
      transformDFGPintoBPMN();
      if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
    } catch (Exception e) {
      propagateExecutionFailure(e);
      discoveryRoute = "safe-dfg";
      System.out.println(
          "ERROR - something went wrong translating DFG to BPMN, trying a second time");
      e.printStackTrace();
      try {
        dfgp =
            new DirectlyFollowGraphPlus(
                this.log,
                percentileFrequencyThreshold,
                parallelismsThreshold,
                filterType,
                parallelismsFirst);
        dfgp.buildSafeDFGP();
        transformDFGPintoBPMN();
        if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
      } catch (Exception ee) {
        propagateExecutionFailure(ee);
        discoveryRoute = "bare-dfg";
        System.out.println("ERROR - nothing to do, returning the bare DFGP");
        return dfgp.convertIntoBPMNDiagramWithOriginalLabels();
      }
    }

    return bpmnDiagram;
  }

  public BPMNDiagram mineBPMNModel(
      SimpleLog log,
      XEventClassifier xEventClassifier,
      double percentileFrequencyThreshold,
      double parallelismsThreshold,
      DFGPUIResult.FilterType filterType,
      boolean parallelismsFirst,
      boolean replaceIORs,
      boolean removeLoopActivities,
      SplitMinerUIResult.StructuringTime structuringTime) {
    discoveryRoute = "standard";
    ExecutionChecks.check();
    this.replaceIORs = replaceIORs;
    this.removeLoopActivities = removeLoopActivities;
    this.structuringTime = structuringTime;

    this.log = log;

    generateDFGP(
        percentileFrequencyThreshold, parallelismsThreshold, filterType, parallelismsFirst);
    try {
      transformDFGPintoBPMN();
      if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
    } catch (Exception e) {
      propagateExecutionFailure(e);
      discoveryRoute = "safe-dfg";
      System.out.println(
          "ERROR - something went wrong translating DFG to BPMN, trying a second time");
      e.printStackTrace();
      try {
        dfgp =
            new DirectlyFollowGraphPlus(
                log,
                percentileFrequencyThreshold,
                parallelismsThreshold,
                filterType,
                parallelismsFirst);
        dfgp.buildSafeDFGP();
        transformDFGPintoBPMN();
        if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
      } catch (Exception ee) {
        propagateExecutionFailure(ee);
        discoveryRoute = "bare-dfg";
        System.out.println("ERROR - nothing to do, returning the bare DFGP");
        return dfgp.convertIntoBPMNDiagramWithOriginalLabels();
      }
    }

    return bpmnDiagram;
  }

  private void generateDFGP(
      double percentileFrequencyThreshold,
      double parallelismsThreshold,
      DFGPUIResult.FilterType filterType,
      boolean parallelismsFirst) {
    dfgp =
        new DirectlyFollowGraphPlus(
            log,
            percentileFrequencyThreshold,
            parallelismsThreshold,
            filterType,
            parallelismsFirst);
    dfgp.setOracle(!parallelismsFirst);
    dfgp.buildDFGP();
  }

  public BPMNDiagram discoverFromDFGP(DirectlyFollowGraphPlus idfgp) {
    discoveryRoute = "standard";
    ExecutionChecks.check();
    this.log = idfgp.getSimpleLog();
    dfgp = idfgp;
    try {
      transformDFGPintoBPMN();
      if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
    } catch (Exception e) {
      propagateExecutionFailure(e);
      discoveryRoute = "bare-dfg";
      System.out.println("ERROR - something went wrong translating DFG to BPMN");
      e.printStackTrace();
      return dfgp.convertIntoBPMNDiagramWithOriginalLabels();
    }
    return bpmnDiagram;
  }

  public BPMNDiagram discoverFromSDFG(SimpleDirectlyFollowGraph sdfg) throws Exception {
    discoveryRoute = "standard";
    ExecutionChecks.check();
    this.log = sdfg.getSimpleLog();
    dfgp = sdfg;
    transformDFGPintoBPMN();
    if (structuringTime == SplitMinerUIResult.StructuringTime.POST) structure();
    return bpmnDiagram;
  }

  private void transformDFGPintoBPMN() {
    DiagramHandler helper = new DiagramHandler();
    BPMNNode entry = null;
    BPMNNode exit = null;

    gateCounter = Integer.MIN_VALUE;

    //        we retrieve the starting BPMN diagram from the DFGP,
    //        it is a DFGP with start and end events, but no gateways
    bpmnDiagram = dfgp.convertIntoBPMNDiagram();
    candidateJoins = new HashMap<>();

    //        there are only two events in the initial BPMN diagram,
    //        one is the START and by exclusion the second is the END
    for (Event e : bpmnDiagram.getEvents())
      if (e.getEventType() == Event.EventType.START) entry = e;
      else exit = e;

    if (entry == null || exit == null) {
      //            this should never happen
      System.out.println(
          "ERROR - entry(" + entry + ") OR exit(" + exit + ") not found in the DFGP-diagram");
      return;
    }

    //        we start the transformation of the DFGP into BPMN by generating the splits
    //        generateBitmatrixSplits();
    generateSplits(entry, exit);

    //        after generating the split hierarchy we should have only SPLITs,
    //        however, it may happen that some JOINs are generated as well (due to shared future)
    //        it is important that we do not leave any gateway that is both a SPLIT and a JOIN
    helper.removeJoinSplit(bpmnDiagram);

    //        at this point, all the splits were generated, along with just a few joins
    //        now we focus only on the joins. we use the RPST in order to place INCLUSIVE joins
    //        which will be turned into AND or XOR joins later
    //        System.out.println("SplitMiner - generating SESE joins ...");
    bondsEntries = new HashSet<>();
    rigidsEntries = new HashSet<>();
    while (generateSESEjoins())
      ;

    //        this second method adds the remaining joins, which were no entry neither exits of any
    // RPST node
    //        System.out.println("SplitMiner - generating inner joins ...");
    generateInnerJoins();

    //        if( structuringTime == SplitMinerUIResult.StructuringTime.PRE ) structure();
    //        helper.removeEmptyParallelFlows(bpmnDiagram);
    helper.fixSoundness(bpmnDiagram);

    //        finally, we turn all the inclusive joins placed, into proper joins: ANDs or XORs
    //        System.out.println("SplitMiner - turning inclusive joins ...");
    replaceIORs(helper);

    updateLabels(this.log.getEvents());

    if (removeLoopActivities) helper.removeLoopActivityMarkers(bpmnDiagram);
  }

  private void generateSplits(BPMNNode entry, BPMNNode exit) {
    HashMap<Integer, BPMNNode> mapping = new HashMap<>();
    BPMNNode tgt;
    ArrayList<BPMNNode> toVisit = new ArrayList<>();
    HashSet<BPMNNode> visited = new HashSet<>();

    HashSet<Integer> successors;
    HashSet<BPMNEdge<? extends BPMNNode, ? extends BPMNNode>> removableEdges;

    Oracle oracle = new Oracle();
    OracleItem oracleItem;
    OracleItem finalOracleItem;
    HashSet<OracleItem> oracleItems;

    //        we perform a breadth-first exploration of the DFGP-diagram
    //        every time we find a node with multiple outgoing edges we stop
    //        and we generate the corresponding hierarchy of gateways

    toVisit.add(0, entry);
    while (toVisit.size() != 0) {
      ExecutionChecks.check();
      entry = toVisit.remove(0);
      visited.add(entry);
      //            System.out.println("DEBUG - visiting: " + entry.getLabel());

      if (entry == exit) continue;

      if (bpmnDiagram.getOutEdges(entry).size() > 1) {
        //                entry is a node with multiple outgoing edges

        successors = new HashSet<>();
        removableEdges = new HashSet<>();
        List<BPMNEdge<? extends BPMNNode, ? extends BPMNNode>> outgoing = new ArrayList<>(bpmnDiagram.getOutEdges(entry));
        outgoing.sort((a,b) -> a.getTarget().getLabel().compareTo(b.getTarget().getLabel()));
        for (BPMNEdge<? extends BPMNNode, ? extends BPMNNode> oe : outgoing) {
          tgt = oe.getTarget();
          //                    we remove all the outgoing edges, because we will restore them with
          // the split gateways
          removableEdges.add(oe);
          successors.add(Integer.valueOf(tgt.getLabel()));
          mapping.put(Integer.valueOf(tgt.getLabel()), tgt);
          if (!toVisit.contains(tgt) && !visited.contains(tgt)) toVisit.add(tgt);
        }

        for (BPMNEdge<? extends BPMNNode, ? extends BPMNNode> e : removableEdges)
          bpmnDiagram.removeEdge(e);

        //                to decide the hierarchy of the gateways we use an Oracle item
        //                an Oracle item is a string of the type past|future
        //                more info about this object in its own class
        oracleItems = new HashSet<>();
        for (int a : successors) {
          //                    we generate one Oracle item for each successor of the entry
          //                    the successor will be the past
          oracleItem = new OracleItem();
          oracleItem.fillPast(a);

          //                    then we fill its future with all the successors which are in a
          // concurrency relationship with it
          //                    if a successor is not concurrent, it means it will we exclusive or
          // directly follow
          //                    if exclusive we do not have to care about it
          //                    if directly follow, it will be processed later
          for (int b : successors)
            if ((a != b) && (dfgp.areConcurrent(a, b))) oracleItem.fillFuture(b);

          oracleItem.engrave();
          oracleItems.add(oracleItem);
        }

        finalOracleItem = oracle.getFinalOracleItem(oracleItems);

        //                the finalOracleItem is a matryoshka containing the info about the gateway
        // hierarchy
        //                the following method will explore inside-out this matryoshka and will
        // place the gateways accordingly
        //                the entry will be the last node to be linked to the outer gateway of the
        // hierarchy
        generateSplitsHierarchy(entry, finalOracleItem, mapping);
      } else {
        //                we save the only successor of the src
        tgt = ((new ArrayList<>(bpmnDiagram.getOutEdges(entry))).get(0)).getTarget();
        if (!toVisit.contains(tgt) && !visited.contains(tgt)) toVisit.add(tgt);
      }
    }
  }

  private void generateSplitsHierarchy(
      BPMNNode entry, OracleItem nextOracleItem, Map<Integer, BPMNNode> mapping) {
    //        first of all we retrieve the type of the gateway we should place
    Gateway.GatewayType type = nextOracleItem.getGateType();
    BPMNNode node;
    Integer nodeCode;
    Gateway gate;
    Gateway candidateJoin;

    //        System.out.println("DEBUG - generating split from Oracle ~ [xor|and]: " +
    // nextOracleItem + " ~ [" + nextOracleItem.getXorBrothers().size() + "|" +
    // nextOracleItem.getAndBrothers().size() + "]");

    if (candidateJoins.containsKey(nextOracleItem.toString())) {
      //            these are joins, they are created considering the fact they share the same
      // future (finalOracleItem)
      candidateJoin = candidateJoins.get(nextOracleItem.toString());
      //            System.out.println("DEBUG - found " + candidateJoin.getGatewayType() + " join
      // for the Oracle item: " + nextOracleItem.toString());
      bpmnDiagram.addFlow(entry, candidateJoin, "");
      return;
    }

    if (type == null) {
      //            if the type was null, it means we reached a simple activity, so we can link the
      // entry with the activity
      nodeCode = nextOracleItem.getNodeCode();
      if (nodeCode != null) {
        node = mapping.get(nodeCode);
        bpmnDiagram.addFlow(entry, node, "");
      } else
        System.out.println(
            "ERROR - found an oracle item without brother and more than one element in its past");
      return;
    }

    gate = bpmnDiagram.addGateway(Integer.toString(gateCounter++), type);
    bpmnDiagram.addFlow(entry, gate, "");
    for (OracleItem next : OracleItem.stableOrder(nextOracleItem.getXorBrothers()))
      generateSplitsHierarchy(gate, next, mapping);
    for (OracleItem next : OracleItem.stableOrder(nextOracleItem.getAndBrothers()))
      generateSplitsHierarchy(gate, next, mapping);

    candidateJoins.put(nextOracleItem.toString(), gate);
  }

  private boolean generateSESEjoins() {
    ExecutionChecks.check();
    BpmnStructuralOrder order = new BpmnStructuralOrder(bpmnDiagram);
    List<Flow> originalFlows = orderedFlows(bpmnDiagram.getFlows((Swimlane) null), order);
    Map<String, BPMNNode> nodes = new HashMap<>();
    Map<BPMNNode, Vertex> vertices = new IdentityHashMap<>();
    Map<String, Gateway.GatewayType> gates = new HashMap<>();
    Map<String, List<Flow>> originalIncoming = new HashMap<>();
    Map<String, List<Flow>> originalOutgoing = new HashMap<>();
    IDirectedGraph<DirectedEdge, Vertex> graph = new DirectedGraph();
    for (Flow flow : originalFlows) {
      ExecutionChecks.check();
      for (BPMNNode node : Arrays.asList(flow.getSource(), flow.getTarget())) {
        if (vertices.containsKey(node)) continue;
        if (nodes.put(node.getLabel(), node) != null)
          throw new ReproducibilityException("REPRODUCIBILITY_SPLIT_DUPLICATE_INTERNAL_LABEL");
        Vertex vertex = new Vertex(node.getLabel());
        // Identity must be fixed before insertion into JBPT's hash collections.
        vertex.setId("bpmn:" + order.index(node));
        vertices.put(node, vertex);
        if (node instanceof Gateway) gates.put(node.getLabel(), ((Gateway) node).getGatewayType());
      }
      graph.addEdge(vertices.get(flow.getSource()), vertices.get(flow.getTarget()));
      originalIncoming.computeIfAbsent(flow.getTarget().getLabel(), k -> new ArrayList<>()).add(flow);
      originalOutgoing.computeIfAbsent(flow.getSource().getLabel(), k -> new ArrayList<>()).add(flow);
    }

    // Preserve the original bottom-up hierarchy, with structural ordering of siblings.
    RPST rpst = new RPST(graph);
    LinkedList<RPSTNode> toAnalize = new LinkedList<>();
    toAnalize.add(rpst.getRoot());
    List<RPSTNode> rpstBottomUpHierarchy = new ArrayList<>();
    Set<RPSTNode> loops = Collections.newSetFromMap(new IdentityHashMap<RPSTNode,Boolean>());
    Set<RPSTNode> rigids = Collections.newSetFromMap(new IdentityHashMap<RPSTNode,Boolean>());
    Map<RPSTNode, String> fragmentKeys = new IdentityHashMap<>();
    Map<RPSTNode, List<Flow>> fragmentFlows = new IdentityHashMap<>();
    while (!toAnalize.isEmpty()) {
      ExecutionChecks.check();
      RPSTNode root = toAnalize.removeFirst();
      List<RPSTNode> children = new ArrayList<RPSTNode>(rpst.getChildren(root));
      for (RPSTNode child : children) {
        fragmentFlows.computeIfAbsent(child, n -> originalFragmentFlows(n, originalOutgoing));
        fragmentKeys.computeIfAbsent(child, n -> fragmentKey(n, nodes, fragmentFlows.get(n), order));
      }
      children.sort(Comparator.comparing(fragmentKeys::get));
      for (RPSTNode n : children) {
        switch (n.getType()) {
          case T: break;
          case P: toAnalize.addLast(n); break;
          case R: rigids.add(n);
          case B:
            String entry = n.getEntry().getName(), exit = n.getExit().getName();
            if (!gates.containsKey(exit)) rpstBottomUpHierarchy.add(0, n);
            else if (!gates.containsKey(entry)) {
              rpstBottomUpHierarchy.add(0, n);
              loops.add(n);
            } else if (n.getType() == TCType.R) rigidsEntries.add((Gateway) nodes.get(entry));
            else bondsEntries.add((Gateway) nodes.get(entry));
            toAnalize.addLast(n);
            break;
          default: break;
        }
      }
    }

    Set<String> changed = new HashSet<>();
    int counter = 0;
    for (RPSTNode rpstNode : rpstBottomUpHierarchy) {
      ExecutionChecks.check();
      String entry = rpstNode.getEntry().getName(), exit = rpstNode.getExit().getName();
      boolean isLoop = loops.contains(rpstNode), isRigid = rigids.contains(rpstNode);
      String gatify = isLoop ? entry : exit, matchingGate = isLoop ? exit : entry;
      if (changed.contains(gatify)) continue;
      Gateway.GatewayType type = isRigid ? Gateway.GatewayType.INCLUSIVE : gates.get(matchingGate);
      if (isLoop) type = Gateway.GatewayType.DATABASED;
      Set<String> fragmentSources = new HashSet<>();
      for (Flow flow : fragmentFlows.get(rpstNode))
        if (flow.getTarget().getLabel().equals(gatify)) fragmentSources.add(flow.getSource().getLabel());
      List<Flow> rewired = new ArrayList<>();
      for (Flow flow : originalIncoming.getOrDefault(gatify, Collections.<Flow>emptyList()))
        if (isLoop || fragmentSources.contains(flow.getSource().getLabel())) rewired.add(flow);
      if (rewired.isEmpty()) continue;
      changed.add(gatify);
      Gateway join = bpmnDiagram.addGateway(Integer.toString(gateCounter++), type);
      bpmnDiagram.addFlow(join, nodes.get(gatify), "");
      counter++;
      // Use original flows, including real edges omitted during RPST normalization.
      // Loops include all incoming flows, including those outside their fragment.
      for (Flow flow : rewired) {
        ExecutionChecks.check();
        Flow replacement = bpmnDiagram.addFlow(flow.getSource(), join, flow.getLabel());
        replacement.setConditionExpression(flow.getConditionExpression());
        bpmnDiagram.removeEdge(flow);
      }
    }
    return counter > 0;
  }

  private static List<Flow> orderedFlows(Collection<Flow> flows, BpmnStructuralOrder order) {
    List<Flow> result = new ArrayList<>(flows);
    result.sort(Comparator.comparingInt((Flow f) -> order.index(f.getSource()))
        .thenComparingInt(f -> order.index(f.getTarget()))
        .thenComparing(f -> f.getLabel(), Comparator.nullsFirst(Comparator.naturalOrder()))
        .thenComparing(f -> f.getConditionExpression(), Comparator.nullsFirst(Comparator.naturalOrder())));
    return result;
  }

  private static List<Flow> originalFragmentFlows(RPSTNode fragment, Map<String, List<Flow>> outgoing) {
    Set<String> vertices = new HashSet<>();
    for (Object item : fragment.getFragment().getVertices()) vertices.add(((Vertex)item).getName());
    Set<String> represented = new HashSet<>();
    for (Object item : fragment.getFragment().getEdges()) {
      de.hpi.bpt.graph.abs.AbstractDirectedEdge edge = (de.hpi.bpt.graph.abs.AbstractDirectedEdge)item;
      represented.add(edge.getSource().getName() + ":" + edge.getTarget().getName());
    }
    List<Flow> result = new ArrayList<>();
    boolean component = fragment.getType() == TCType.B || fragment.getType() == TCType.R;
    for (String src : vertices) for (Flow flow : outgoing.getOrDefault(src, Collections.<Flow>emptyList())) {
      ExecutionChecks.check();
      String tgt = flow.getTarget().getLabel();
      // Bonds/rigids contain all original flows internal to their component. A polygon
      // or trivial child represents its own branch, so do not pull in sibling branches.
      if (vertices.contains(tgt) && (component || represented.contains(src + ":" + tgt))) result.add(flow);
    }
    return result;
  }

  private static String fragmentKey(RPSTNode fragment, Map<String, BPMNNode> nodes,
      List<Flow> flows, BpmnStructuralOrder order) {
    ExecutionChecks.check();
    SortedSet<String> edges = new TreeSet<>();
    for (Flow flow : flows) edges.add(order.index(flow.getSource()) + ":" + order.index(flow.getTarget()));
    return fragment.getType() + ":" + order.index(nodes.get(fragment.getEntry().getName()))
        + ":" + order.index(nodes.get(fragment.getExit().getName())) + ":" + edges;
  }


  private void generateInnerJoins() {
    HashSet<BPMNEdge<? extends BPMNNode, ? extends BPMNNode>> removableEdges;
    BpmnStructuralOrder order = new BpmnStructuralOrder(bpmnDiagram);
    List<BPMNNode> nodes = new ArrayList<>(bpmnDiagram.getNodes());
    nodes.sort(order.comparator());
    Gateway gate;
    int counter = 0;

    //        all the activities found with multiple incoming edges are turned into inclusive joins
    //        these activities are inside RIGID fragments of the BPMN model
    for (BPMNNode n : nodes) {
      removableEdges = new HashSet<>(bpmnDiagram.getInEdges(n));
      if ((removableEdges.size() <= 1) || (n instanceof Gateway)) continue;
      gate = bpmnDiagram.addGateway(Integer.toString(gateCounter++), Gateway.GatewayType.INCLUSIVE);
      counter++;
      bpmnDiagram.addFlow(gate, n, "");
      for (BPMNEdge<? extends BPMNNode, ? extends BPMNNode> e : removableEdges) {
        bpmnDiagram.removeEdge(e);
        bpmnDiagram.addFlow(e.getSource(), gate, "");
      }
    }
    //        System.out.println("DEBUG - inner joins placed: " + counter );
  }

  private void replaceIORs(DiagramHandler helper) {
    bondsEntries.removeAll(rigidsEntries);
    GatewayMap gatemap = new GatewayMap(bondsEntries, replaceIORs);
    //        System.out.println("DEBUG - doing the magic ...");
    if (gatemap.generateMap(bpmnDiagram)) {
      gatemap.detectAndReplaceIORs();
      gatemap.checkANDLoops(true);
    } else System.out.println("ERROR - something went wrong initializing the gateway map");

    int counter;
    int[] potentialORs;
    int tgt1, tgt2;
    boolean ORs = false;
    int columns;
    if (!replaceIORs) {
      potentialORs = dfgp.getPotentialORs();
      columns = (int) Math.sqrt(potentialORs.length);
      for (Gateway g : bpmnDiagram.getGateways()) {
        if (g.getGatewayType() == Gateway.GatewayType.PARALLEL
            && bpmnDiagram.getOutEdges(g).size() > 1) {
          counter = 0;
          for (BPMNEdge<? extends BPMNNode, ? extends BPMNNode> oe1 : bpmnDiagram.getOutEdges(g))
            for (BPMNEdge<? extends BPMNNode, ? extends BPMNNode> oe2 : bpmnDiagram.getOutEdges(g))
              if ((oe1.getTarget() == oe2.getTarget())
                  || (oe1.getTarget() instanceof Gateway)
                  || (oe2.getTarget() instanceof Gateway)) continue;
              else {
                tgt1 = Integer.valueOf(oe1.getTarget().getLabel());
                tgt2 = Integer.valueOf(oe2.getTarget().getLabel());
                if (potentialORs[(tgt1 * columns) + tgt2] > 0) counter++;
              }
          if (counter > bpmnDiagram.getOutEdges(g).size()) {
            ORs = true;
            g.setGatewayType(Gateway.GatewayType.INCLUSIVE);
          }
        }
      }
      if (ORs) helper.matchORs(bpmnDiagram);
    }
  }

  private void structure() {
    StructuringService ss = new StructuringService();
    BPMNDiagram structureDiagram = ss.structureDiagram(bpmnDiagram);
    bpmnDiagram = structureDiagram;
  }

  private void updateLabels(Map<Integer, String> events) {
    //        this method just replace the labels of the activities in the BPMN diagram,
    //        that so far have been numbers (in order to speed up the computation complexity)
    DiagramHandler helper = new DiagramHandler();
    BPMNDiagram duplicateDiagram = new BPMNDiagramImpl(bpmnDiagram.getLabel());
    HashMap<BPMNNode, BPMNNode> originalToCopy = new HashMap<>();
    BPMNNode src, tgt;
    BPMNNode copy;
    String label;

    for (BPMNNode n : bpmnDiagram.getNodes()) {
      if (n instanceof Activity) label = events.get(Integer.valueOf(n.getLabel()));
      else label = "";
      copy = helper.copyNode(duplicateDiagram, n, label);
      if (copy != null) originalToCopy.put(n, copy);
      else System.out.println("ERROR - diagram labels updating failed [1].");
    }

    for (Flow f : bpmnDiagram.getFlows()) {
      src = originalToCopy.get(f.getSource());
      tgt = originalToCopy.get(f.getTarget());

      if (src != null && tgt != null) duplicateDiagram.addFlow(src, tgt, "");
      else System.out.println("ERROR - diagram labels updating failed [2].");
    }
    bpmnDiagram = duplicateDiagram;
  }
}
