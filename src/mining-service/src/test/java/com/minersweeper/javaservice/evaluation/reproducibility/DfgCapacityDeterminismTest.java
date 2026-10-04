package com.minersweeper.javaservice.evaluation.reproducibility;

import static org.junit.Assert.*;
import java.lang.reflect.*;
import java.util.*;
import org.junit.Test;
import processmining.splitminer.dfgp.*;

/** Check witness choices, not merely deterministic hashes of an already different graph. */
public class DfgCapacityDeterminismTest {
    private static final class Fixture extends DirectlyFollowGraphPlus {}

    private static void field(Fixture graph, String name, Object value) throws Exception {
        Field f = DirectlyFollowGraphPlus.class.getDeclaredField(name);
        f.setAccessible(true); f.set(graph, value);
    }
    @SuppressWarnings("unchecked")
    private static Set<DFGEdge> selection(Fixture graph, String method, String field) throws Exception {
        Method m = DirectlyFollowGraphPlus.class.getDeclaredMethod(method);
        m.setAccessible(true); m.invoke(graph);
        Field f = DirectlyFollowGraphPlus.class.getDeclaredField(field);
        f.setAccessible(true); return (Set<DFGEdge>) f.get(graph);
    }
    private static Fixture graph(List<int[]> spec, int seed, List<DFGEdge> all) throws Exception {
        Fixture graph = new Fixture();
        Map<Integer,DFGNode> nodes = new HashMap<>();
        Map<Integer,HashSet<DFGEdge>> outgoing = new HashMap<>(), incoming = new HashMap<>();
        Map<Integer,HashMap<Integer,DFGEdge>> adjacency = new HashMap<>();
        List<Integer> codes = new ArrayList<>(Arrays.asList(0,1,2,3,4,5,6,7));
        Collections.shuffle(codes, new Random(seed));
        for (int n : codes) {
            nodes.put(n,new DFGNode("activity-"+n,n));
            outgoing.put(n,new HashSet<>()); incoming.put(n,new HashSet<>());
            adjacency.put(n,new HashMap<>());
        }
        List<int[]> shuffled = new ArrayList<>(spec);
        Collections.shuffle(shuffled,new Random(seed*19L));
        for (int[] e : shuffled) {
            DFGEdge edge = new DFGEdge(nodes.get(e[0]),nodes.get(e[1]),e[2]);
            all.add(edge);outgoing.get(e[0]).add(edge);incoming.get(e[1]).add(edge);
            adjacency.get(e[0]).put(e[1],edge);
        }
        field(graph,"nodes",nodes);field(graph,"outgoings",outgoing);field(graph,"incomings",incoming);
        field(graph,"dfgp",adjacency);
        field(graph,"edges",new HashSet<>(all));field(graph,"startcode",0);field(graph,"endcode",7);
        field(graph,"percentileFrequencyThreshold",.8);
        return graph;
    }
    private static SortedSet<String> edges(Collection<DFGEdge> edges) {
        SortedSet<String> result = new TreeSet<>();
        for (DFGEdge e : edges) result.add(e.getSourceCode()+":"+e.getTargetCode()+":"+e.getFrequency());
        return result;
    }
    // Independent Bellman relaxation of widest-path capacities, in both directions.
    private static int[] capacities(Collection<DFGEdge> edges, boolean backward) {
        int[] result = new int[8];result[backward ? 7 : 0]=Integer.MAX_VALUE;
        boolean changed;
        do {
            changed=false;
            for (DFGEdge edge : edges) {
                int src=backward?edge.getTargetCode():edge.getSourceCode();
                int tgt=backward?edge.getSourceCode():edge.getTargetCode();
                int value=Math.min(result[src],edge.getFrequency());
                if(value>result[tgt]){result[tgt]=value;changed=true;}
            }
        } while(changed);
        return result;
    }
    @Test public void tiedCyclicGraphsPreserveCapacitiesAndIgnoreInsertionOrder() throws Exception {
        for (int example=0; example<20; example++) {
            Random random=new Random(example);
            List<int[]> spec=new ArrayList<>();
            Set<String> pairs=new HashSet<>();
            for(int src=0;src<7;src++) {
                spec.add(new int[]{src,src+1,1+random.nextInt(3)});pairs.add(src+":"+(src+1));
            }
            for(int src=1;src<7;src++)for(int tgt=1;tgt<7;tgt++)
                if(random.nextBoolean() && pairs.add(src+":"+tgt))spec.add(new int[]{src,tgt,1+random.nextInt(3)});
            SortedSet<String> expected=null, connectedExpected=null, filteredExpected=null;
            for(int permutation=0;permutation<16;permutation++) {
                List<DFGEdge> all=new ArrayList<>();Fixture g=graph(spec,permutation,all);
                Set<DFGEdge> selected=selection(g,"bestEdgesOnMaxCapacities","bestEdges");
                Set<DFGEdge> connected=selection(g,"bestEdgesOnMaxCapacitiesForConnectedness","untouchableEdges");
                for(boolean reverse:new boolean[]{false,true}) {
                    assertArrayEquals(capacities(all,reverse),capacities(selected,reverse));
                    assertArrayEquals(capacities(all,reverse),capacities(connected,reverse));
                }
                g.filterWithGuarantees();
                for(boolean reverse:new boolean[]{false,true})
                    assertArrayEquals(capacities(all,reverse),capacities(g.getEdges(),reverse));
                if(expected==null){expected=edges(selected);connectedExpected=edges(connected);filteredExpected=edges(g.getEdges());}
                assertEquals(expected,edges(selected));assertEquals(connectedExpected,edges(connected));
                assertEquals(filteredExpected,edges(g.getEdges()));
            }
        }
    }
}
