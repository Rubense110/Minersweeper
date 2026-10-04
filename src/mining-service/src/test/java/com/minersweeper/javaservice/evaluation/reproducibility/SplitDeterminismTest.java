package com.minersweeper.javaservice.evaluation.reproducibility;

import static org.junit.Assert.*;
import java.util.*;
import java.lang.reflect.*;
import java.net.*;
import org.junit.Test;
import org.deckfour.xes.classification.XEventNameClassifier;
import org.deckfour.xes.extension.std.XConceptExtension;
import org.deckfour.xes.factory.XFactoryNaiveImpl;
import org.deckfour.xes.model.*;
import org.processmining.models.graphbased.directed.bpmn.*;
import org.processmining.models.graphbased.directed.bpmn.elements.*;
import processmining.splitminer.SplitMiner;
import processmining.splitminer.dfgp.DirectlyFollowGraphPlus;
import processmining.splitminer.oracle.*;
import processmining.splitminer.ui.dfgp.DFGPUIResult.FilterType;
import processmining.splitminer.ui.miner.SplitMinerUIResult.StructuringTime;
import bpmn.helper.GatewayMap;
import de.hpi.bpt.graph.DirectedEdge;
import de.hpi.bpt.graph.algo.rpst.RPSTNode;
import de.hpi.bpt.graph.algo.tctree.TCType;
import de.hpi.bpt.hypergraph.abs.Vertex;
import com.minersweeper.javaservice.evaluation.*;

public class SplitDeterminismTest {
    private static String structuralSignature(BPMNDiagram diagram) {
        BpmnStructuralOrder order=new BpmnStructuralOrder(diagram);
        List<String> nodes=new ArrayList<>(),flows=new ArrayList<>();
        for(BPMNNode node:diagram.getNodes()) {
            String color=node instanceof Gateway ? ((Gateway)node).getGatewayType().toString()
                : node instanceof Event ? ((Event)node).getEventType().toString() : node.getLabel();
            nodes.add(order.index(node)+":"+color);
        }
        for(Flow flow:diagram.getFlows())flows.add(order.index(flow.getSource())+":"+
            order.index(flow.getTarget())+":"+flow.getLabel()+":"+flow.getConditionExpression());
        Collections.sort(nodes);Collections.sort(flows);return nodes+" "+flows;
    }

    @Test public void nestedBondsWithADirectBranchProduceTheSameJoinsAcrossConstructionOrders() throws Exception {
        String expected=null;
        for(int seed=0;seed<32;seed++) {
            BPMNDiagram diagram=new BPMNDiagramImpl("nested-bonds");
            Map<String,BPMNNode> nodes=new HashMap<>();
            List<String> roles=new ArrayList<>(Arrays.asList("start","end","A","B","C","F","outer","inner"));
            Collections.shuffle(roles,new Random(seed));
            for(String role:roles) {
                BPMNNode node;
                if(role.equals("start") || role.equals("end"))
                    node=diagram.addEvent(role,role.equals("start")?Event.EventType.START:Event.EventType.END,
                        Event.EventTrigger.NONE,role.equals("start")?Event.EventUse.CATCH:Event.EventUse.THROW,true,null);
                else if(role.equals("outer") || role.equals("inner"))
                    node=diagram.addGateway(role+"_"+seed,Gateway.GatewayType.DATABASED);
                else node=diagram.addActivity(role,false,false,false,false,false);
                nodes.put(role,node);
            }
            List<String[]> links=new ArrayList<>(Arrays.asList(new String[]{"start","outer"},
                new String[]{"outer","A"},new String[]{"A","inner"},new String[]{"outer","F"},
                new String[]{"F","end"},new String[]{"inner","B"},new String[]{"B","end"},
                new String[]{"inner","C"},new String[]{"C","end"},new String[]{"inner","end"}));
            Collections.shuffle(links,new Random(seed*37L));
            for(String[] link:links) {
                Flow flow=diagram.addFlow(nodes.get(link[0]),nodes.get(link[1]),link[0].equals("inner")&&link[1].equals("end")?"direct":"");
                if(flow.getLabel().equals("direct"))flow.setConditionExpression("keep me");
            }
            SplitMiner miner=new SplitMiner();
            for(String field:Arrays.asList("bpmnDiagram","gateCounter","bondsEntries","rigidsEntries")) {
                Field f=SplitMiner.class.getDeclaredField(field);f.setAccessible(true);
                f.set(miner,field.equals("bpmnDiagram")?diagram:field.equals("gateCounter")?Integer.MIN_VALUE:new HashSet<Gateway>());
            }
            Method generate=SplitMiner.class.getDeclaredMethod("generateSESEjoins");generate.setAccessible(true);
            int iterations=0;while((Boolean)generate.invoke(miner))assertTrue(++iterations<20);
            Method inner=SplitMiner.class.getDeclaredMethod("generateInnerJoins");inner.setAccessible(true);inner.invoke(miner);
            String signature=structuralSignature(diagram);if(expected==null)expected=signature;assertEquals(expected,signature);
            assertEquals(4,diagram.getGateways().size());
            boolean preserved=false;
            for(Flow flow:diagram.getFlows())if(flow.getLabel().equals("direct")) {
                preserved=true;assertSame(nodes.get("inner"),flow.getSource());
                assertTrue(flow.getTarget() instanceof Gateway);assertEquals("keep me",flow.getConditionExpression());
            }
            assertTrue(preserved);
        }
    }
    private static final class Fragment extends RPSTNode<DirectedEdge,Vertex> {
        Fragment(TCType type) { setType(type); }
    }

    @Test public void bondsRecoverRealDirectBranchesWithoutPullingSiblingEdgesIntoPolygons() throws Exception {
        BPMNDiagram diagram = new BPMNDiagramImpl("projection");
        Activity a = diagram.addActivity("A",false,false,false,false,false);
        Activity b = diagram.addActivity("B",false,false,false,false,false);
        Activity c = diagram.addActivity("C",false,false,false,false,false);
        Activity outside = diagram.addActivity("outside",false,false,false,false,false);
        Flow ab = diagram.addFlow(a,b,"ab"), bc = diagram.addFlow(b,c,"bc");
        Flow direct = diagram.addFlow(a,c,"direct");
        Flow external = diagram.addFlow(a,outside,"external");
        Map<String,List<Flow>> outgoing = new HashMap<>();
        outgoing.put("A",Arrays.asList(ab,direct,external));outgoing.put("B",Arrays.asList(bc));
        Method projection = SplitMiner.class.getDeclaredMethod("originalFragmentFlows",RPSTNode.class,Map.class);
        projection.setAccessible(true);
        for (TCType type : Arrays.asList(TCType.B,TCType.R,TCType.P)) {
            Fragment fragment = new Fragment(type);
            Vertex va=new Vertex("A"),vb=new Vertex("B"),vc=new Vertex("C");
            fragment.getFragment().addEdge(va,vb);fragment.getFragment().addEdge(vb,vc);
            @SuppressWarnings("unchecked") List<Flow> real = (List<Flow>)projection.invoke(null,fragment,outgoing);
            assertTrue(real.contains(ab));assertTrue(real.contains(bc));assertFalse(real.contains(external));
            assertEquals(type!=TCType.P,real.contains(direct));
        }
    }
    private static OracleItem leaf(int activity, int... future) {
        OracleItem result = new OracleItem(); result.fillPast(activity);
        for (int next : future) result.fillFuture(next);
        result.engrave(); return result;
    }
    private static Set<OracleItem> identityItems(OracleItem... items) {
        Set<OracleItem> result = Collections.newSetFromMap(new IdentityHashMap<OracleItem,Boolean>());
        result.addAll(Arrays.asList(items)); return result;
    }

    @Test public void forcedDistanceTiesIgnoreInputOrderAndObjectIdentity() {
        String expected = null;
        for (int seed=0; seed<40; seed++) {
            List<OracleItem> leaves = new ArrayList<>(Arrays.asList(leaf(1,4),leaf(2,5),leaf(3,6)));
            Collections.shuffle(leaves,new Random(seed));
            Set<OracleItem> input = new LinkedHashSet<>(leaves);
            OracleItem root = new Oracle().getFinalOracleItem(input);
            if (expected == null) expected = root.structuralKey();
            assertEquals(expected,root.structuralKey());
            assertEquals(3,input.size()); // caller input is not consumed
        }
    }

    @Test public void identicalCandidatesArePreservedAndEqualityHashAgree() {
        OracleItem a=leaf(1,9), b=leaf(1,9);
        assertEquals(a,b); assertEquals(a.hashCode(),b.hashCode());
        assertEquals(2,OracleItem.stableOrder(Arrays.asList(a,b)).size());
        OracleItem root=new Oracle().getFinalOracleItem(identityItems(a,b));
        assertEquals(2,root.getXorBrothers().size());
    }

    @Test public void equalSignaturesWithDifferentHierarchiesAreNotCollapsed() {
        OracleItem and=OracleItem.mergeANDs(identityItems(leaf(1,9),leaf(2,9)));
        OracleItem xor=OracleItem.mergeXORs(identityItems(leaf(1,9),leaf(2,9)));
        assertEquals(and,xor); assertNotEquals(and.structuralKey(),xor.structuralKey());
        List<OracleItem> forward=OracleItem.stableOrder(Arrays.asList(and,xor));
        List<OracleItem> reverse=OracleItem.stableOrder(Arrays.asList(xor,and));
        assertSame(forward.get(0),reverse.get(0)); assertEquals(2,forward.size());
        assertEquals(2,new Oracle().getFinalOracleItem(identityItems(and,xor)).getXorBrothers().size());
    }

    @Test public void cyclicHierarchyFailsExplicitly() {
        OracleItem item=leaf(1); item.getXorBrothers().add(item);
        try { item.structuralKey(); fail(); }
        catch(ReproducibilityException error) {
            assertEquals("REPRODUCIBILITY_SPLIT_ORACLE_CYCLE",error.code);
        }
    }

    @Test public void cancellationIsPreserved() {
        Thread.currentThread().interrupt();
        try {
            new Oracle().getFinalOracleItem(identityItems(leaf(1),leaf(2)));
            fail();
        } catch(java.util.concurrent.CancellationException expected) {
            assertTrue(Thread.currentThread().isInterrupted());
        } finally { Thread.interrupted(); }
    }

    @Test public void executionFailureInsideTransformationDoesNotTriggerFallback() {
        SplitMiner miner=new SplitMiner();
        XFactoryNaiveImpl factory=new XFactoryNaiveImpl(); XLog log=factory.createLog();
        XTrace trace=factory.createTrace();
        for (String label : Arrays.asList("A","B","C")) {
            XEvent event=factory.createEvent(); XConceptExtension.instance().assignName(event,label); trace.add(event);
        }
        log.add(trace);
        try(ExecutionChecks.Work work=ExecutionChecks.withinWork(1L)) {
            try {
                miner.mineBPMNModel(log,new XEventNameClassifier(),.5,.5,FilterType.FWG,
                    false,false,false,StructuringTime.NONE);
                fail();
            } catch(ExecutionChecks.WorkLimitExceeded expected) {
                assertEquals("standard",miner.getDiscoveryRoute());
            }
        }
    }

    private static final class FailingDfg extends DirectlyFollowGraphPlus {
        final BPMNDiagram fallback=new BPMNDiagramImpl("fallback");
        int fallbackCalls;
        @Override public BPMNDiagram convertIntoBPMNDiagram() {
            throw new IllegalArgumentException("deliberate transformation failure");
        }
        @Override public BPMNDiagram convertIntoBPMNDiagramWithOriginalLabels() {
            fallbackCalls++; return fallback;
        }
    }

    @Test public void directDfgFallbackRecordsBareRoute() {
        SplitMiner miner=new SplitMiner(); FailingDfg dfg=new FailingDfg();
        assertSame(dfg.fallback,miner.discoverFromDFGP(dfg));
        assertEquals("bare-dfg",miner.getDiscoveryRoute());
        assertEquals(1,dfg.fallbackCalls);
    }

    @Test public void cancelledDirectDfgDoesNotReturnFallback() {
        SplitMiner miner=new SplitMiner(); FailingDfg dfg=new FailingDfg();
        Thread.currentThread().interrupt();
        try {
            miner.discoverFromDFGP(dfg); fail();
        } catch(java.util.concurrent.CancellationException expected) {
            assertEquals(0,dfg.fallbackCalls);
            assertTrue(Thread.currentThread().isInterrupted());
        } finally { Thread.interrupted(); }
    }

    // Supply a classified gateway map to exercise repair independently of DFS loop detection.
    private static final class LoopModel {
        final BPMNDiagram diagram=new BPMNDiagramImpl("test");
        final GatewayMap map=new GatewayMap(false);
        final Map<Gateway,Set<Object>> outgoing=new LinkedHashMap<>(),incoming=new LinkedHashMap<>();
        final List<Gateway> original=new ArrayList<>();
        int flowID;
        Gateway gateway(String label,Gateway.GatewayType type) {
            Gateway gate=diagram.addGateway(label,type);original.add(gate);
            outgoing.put(gate,new HashSet<>());incoming.put(gate,new HashSet<>());return gate;
        }
        void edge(Gateway src,Gateway tgt,boolean loop) throws Exception {
            diagram.addFlow(src,tgt,"");
            Class<?> flowType=Class.forName("bpmn.helper.GatewayMap$GatewayMapFlow");
            Constructor<?> constructor=flowType.getDeclaredConstructor(int.class,Gateway.class,Gateway.class,BPMNNode.class,BPMNNode.class);
            constructor.setAccessible(true);Object flow=constructor.newInstance(++flowID,src,tgt,tgt,src);
            Field flag=flowType.getDeclaredField("loop");flag.setAccessible(true);flag.set(flow,loop);
            outgoing.get(src).add(flow);incoming.get(tgt).add(flow);
        }
        void repair(boolean reverse) throws Exception {
            if(reverse) {
                List<Gateway> keys=new ArrayList<>(outgoing.keySet());Collections.reverse(keys);
                Map<Gateway,Set<Object>> reordered=new LinkedHashMap<>();
                for(Gateway gate:keys)reordered.put(gate,outgoing.get(gate));
                outgoing.clear();outgoing.putAll(reordered);
            }
            field("bpmnDiagram",diagram);field("outgoings",outgoing);field("incomings",incoming);
            map.checkANDLoops(true);
        }
        void field(String name,Object value) throws Exception {
            Field f=GatewayMap.class.getDeclaredField(name);f.setAccessible(true);f.set(map,value);
        }
        boolean connects(BPMNNode src,BPMNNode tgt) {
            for(Flow flow:diagram.getFlows())if(flow.getSource()==src && flow.getTarget()==tgt)return true;
            return false;
        }
    }

    @Test public void xorPropagationRepairsPartialLoopInEitherTraversalOrder() throws Exception {
        for(boolean reverse:new boolean[]{false,true}) {
            LoopModel m=new LoopModel();
            Gateway whole=m.gateway("whole",Gateway.GatewayType.PARALLEL);
            Gateway partial=m.gateway("partial",Gateway.GatewayType.PARALLEL);
            Gateway x=m.gateway("x",Gateway.GatewayType.DATABASED), y=m.gateway("y",Gateway.GatewayType.DATABASED);
            Gateway end=m.gateway("end",Gateway.GatewayType.DATABASED);
            Activity start=m.diagram.addActivity("START",false,false,false,false,false);
            m.diagram.addFlow(start,partial,"");
            m.edge(whole,x,true);m.edge(whole,y,true);m.edge(partial,whole,true);m.edge(partial,end,false);
            m.edge(x,partial,false);m.edge(y,partial,false);
            m.repair(reverse);
            assertEquals(Gateway.GatewayType.DATABASED,whole.getGatewayType());
            assertEquals(Gateway.GatewayType.PARALLEL,partial.getGatewayType());
            Gateway bypass=null;
            for(Gateway gate:m.diagram.getGateways())if(!m.original.contains(gate))bypass=gate;
            assertNotNull(bypass);assertEquals(6,m.diagram.getGateways().size());
            assertTrue(m.connects(start,bypass));assertTrue(m.connects(x,bypass));assertTrue(m.connects(y,bypass));
            assertTrue(m.connects(bypass,whole));assertTrue(m.connects(bypass,partial));
            assertTrue(m.connects(partial,end));assertFalse(m.connects(partial,whole));
        }
    }

    @Test public void xorClosureReachesAllLevelsWithoutTraversalDependence() throws Exception {
        for(boolean reverse:new boolean[]{false,true}) {
            LoopModel m=new LoopModel();
            Gateway first=m.gateway("1",Gateway.GatewayType.PARALLEL);
            Gateway second=m.gateway("2",Gateway.GatewayType.PARALLEL);
            Gateway third=m.gateway("3",Gateway.GatewayType.PARALLEL);
            Gateway x=m.gateway("x",Gateway.GatewayType.DATABASED), y=m.gateway("y",Gateway.GatewayType.DATABASED);
            m.edge(first,x,true);m.edge(first,y,true);
            m.edge(second,first,true);m.edge(second,x,true);
            m.edge(third,second,true);m.edge(third,first,true);
            m.repair(reverse);
            for(Gateway gate:Arrays.asList(first,second,third))assertEquals(Gateway.GatewayType.DATABASED,gate.getGatewayType());
            assertEquals(5,m.diagram.getGateways().size());
        }
    }

    @Test public void interactingRepairsUseOriginalEdgesAndPreserveFlowConditions() throws Exception {
        for(boolean reverse:new boolean[]{false,true}) {
            LoopModel m=new LoopModel();
            Gateway first=m.gateway("first",Gateway.GatewayType.PARALLEL);
            Gateway second=m.gateway("second",Gateway.GatewayType.PARALLEL);
            Gateway x=m.gateway("x",Gateway.GatewayType.DATABASED), end=m.gateway("end",Gateway.GatewayType.DATABASED);
            Activity start=m.diagram.addActivity("START",false,false,false,false,false);
            Flow entering=m.diagram.addFlow(start,first,"enter");entering.setConditionExpression("condition");
            m.edge(first,x,true);m.edge(first,end,false);m.edge(first,second,false);
            m.edge(second,x,true);m.edge(second,end,false);
            m.repair(reverse);
            BPMNNode beforeFirst=null,beforeSecond=null;
            for(Flow flow:m.diagram.getFlows()) {
                if(flow.getSource()==start) {
                    beforeFirst=flow.getTarget();assertEquals("enter",flow.getLabel());
                    assertEquals("condition",flow.getConditionExpression());
                }
                if(flow.getSource()==first && flow.getTarget()!=end)beforeSecond=flow.getTarget();
            }
            assertNotNull(beforeFirst);assertNotNull(beforeSecond);assertNotSame(beforeFirst,beforeSecond);
            assertTrue(m.connects(beforeFirst,first));assertTrue(m.connects(beforeFirst,x));
            assertTrue(m.connects(beforeSecond,second));assertTrue(m.connects(beforeSecond,x));
            assertTrue(m.connects(first,end));assertTrue(m.connects(second,end));
            assertEquals(6,m.diagram.getGateways().size());
        }
    }

    @Test public void parallelCycleWithoutExclusiveSeedDoesNotBecomeXor() throws Exception {
        LoopModel m=new LoopModel();
        Gateway first=m.gateway("1",Gateway.GatewayType.PARALLEL), second=m.gateway("2",Gateway.GatewayType.PARALLEL);
        m.edge(first,first,true);m.edge(first,second,true);m.edge(second,first,true);m.edge(second,second,true);
        m.repair(true);
        assertEquals(Gateway.GatewayType.PARALLEL,first.getGatewayType());
        assertEquals(Gateway.GatewayType.PARALLEL,second.getGatewayType());assertEquals(2,m.diagram.getGateways().size());
    }

    @Test public void structuralRanksIgnoreGatewayNamesAndCreationOrder() {
        Map<String,Integer> expected=null;
        for(int seed=0;seed<15;seed++) {
            BPMNDiagram diagram=new BPMNDiagramImpl("ignored");
            List<String> labels=new ArrayList<>(Arrays.asList("A","B","C"));Collections.shuffle(labels,new Random(seed));
            Map<String,Activity> activities=new HashMap<>();
            for(String label:labels)activities.put(label,diagram.addActivity(label,false,false,false,false,false));
            Gateway gate=diagram.addGateway("generated_"+seed,Gateway.GatewayType.PARALLEL);
            diagram.addFlow(activities.get("A"),gate,"");diagram.addFlow(gate,activities.get("B"),"");diagram.addFlow(gate,activities.get("C"),"");
            BpmnStructuralOrder order=new BpmnStructuralOrder(diagram);
            Map<String,Integer> actual=new TreeMap<>();
            for(String label:labels)actual.put(label,order.index(activities.get(label)));
            actual.put("gate",order.index(gate));
            if(expected==null)expected=actual;assertEquals(expected,actual);
        }
    }

    @Test public void originalSplitClasspathIsRejected() throws Exception {
        URL original=Class.forName("com.raffaeleconforti.conversion.bpmn.BPMNToPetriNetConverter")
            .getProtectionDomain().getCodeSource().getLocation();
        URL service=SplitMinerProvenance.class.getProtectionDomain().getCodeSource().getLocation();
        try(URLClassLoader loader=new URLClassLoader(new URL[]{original,service},null)) {
            try {
                loader.loadClass(SplitMinerProvenance.class.getName()).getMethod("verify").invoke(null);fail();
            } catch(InvocationTargetException error) {
                assertEquals("REPRODUCIBILITY_SPLIT_CLASSPATH_MISMATCH",error.getCause().getClass()
                    .getField("code").get(error.getCause()));
            }
        }
        SplitMinerProvenance.verify();
    }
}
