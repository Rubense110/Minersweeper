package com.minersweeper.javaservice.evaluation.reproducibility;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import com.minersweeper.javaservice.evaluation.ReproducibilityException;
import java.util.*;
import org.processmining.models.graphbased.directed.petrinet.*;
import org.processmining.models.graphbased.directed.petrinet.elements.*;
import org.processmining.models.semantics.petrinet.Marking;

/** Exact colored directed-graph labeling; UUID and non-observable names are ignored.
 * Refinement is an optimization, never an equivalence proof. Residual cells are
 * individualized and searched; only verified twin transpositions are pruned.
 * Search/allocations are bounded: failure is explicit, never a UUID fallback.
 * No net/marking is modified and no dense N*N adjacency matrix is allocated.
 */
public final class CanonicalNetOrder {
    public static final String VERSION = "canonical-net-v1";
    private final List<PetrinetNode> nodes = new ArrayList<PetrinetNode>();
    private final Map<PetrinetNode,Integer> original = new HashMap<PetrinetNode,Integer>();
    private final Map<PetrinetNode,Integer> ranks = new HashMap<PetrinetNode,Integer>();
    private final List<String> labels = new ArrayList<String>();
    private final List<List<Edge>> outgoing = new ArrayList<List<Edge>>();
    private final List<List<Edge>> incoming = new ArrayList<List<Edge>>();
    private long work, allocated;
    private int visits;
    private final long maxWork;
    private String best;
    private int[] bestOrder;

    public CanonicalNetOrder(Petrinet net, Marking initial, List<Marking> finals) {
        this(net, initial, finals, 4_000_000L);
    }
    public CanonicalNetOrder(Petrinet net, Marking initial, List<Marking> finals, long maxWork) {
        this.maxWork = maxWork;
        for (Place p : net.getPlaces()) add(p, "P:" + (initial == null ? 0 : initial.occurrences(p).intValue()));
        for (Transition t : net.getTransitions()) {
            String label = t.getLabel() == null ? "" : t.getLabel();
            add(t, t.isInvisible() ? "T:tau" : "T:visible:" + label.length() + ":" + label);
        }
        for (PetrinetEdge<? extends PetrinetNode,? extends PetrinetNode> e : net.getEdges()) {
            if (!(e instanceof Arc)) throw new ReproducibilityException("REPRODUCIBILITY_UNSUPPORTED_ARC");
            edge(require(e.getSource()), require(e.getTarget()), ((Arc)e).getWeight());
        }
        // Final markings are unordered auxiliary vertices: preserves correlations
        // between tokens across places, even with alternative accepting markings.
        if (finals != null) for (Marking m : finals) {
            if (m == null) throw new IllegalArgumentException("Final marking is required");
            int f = add(null, "F");
            for (Place p : m.baseSet()) edge(f, require(p), m.occurrences(p).intValue());
        }
        if (initial != null) for (Place p : initial.baseSet()) require(p);
        int[] colors = compress(labels.toArray(new String[0]));
        search(colors, 0);
        for (int i=0;i<bestOrder.length;i++) {
            PetrinetNode n = nodes.get(bestOrder[i]);
            if (n != null) ranks.put(n, i);
        }
    }
    private void check() {
        ExecutionChecks.check();
        if (++work > maxWork) throw new ReproducibilityException("REPRODUCIBILITY_ORDER_LIMIT");
    }
    private void reserve(long bytes) {
        check(); allocated += bytes;
        if (allocated > 64L*1024L*1024L) throw new ReproducibilityException("REPRODUCIBILITY_ORDER_LIMIT");
    }
    private int add(PetrinetNode n, String label) {
        reserve(160L + 2L*label.length());
        if (nodes.size() >= 10000) throw new ReproducibilityException("REPRODUCIBILITY_ORDER_LIMIT");
        int i=nodes.size(); nodes.add(n); labels.add(label);
        outgoing.add(new ArrayList<Edge>()); incoming.add(new ArrayList<Edge>());
        if (n != null) original.put(n,i);
        return i;
    }
    private int require(PetrinetNode n) {
        Integer i=original.get(n);
        if(i==null) throw new IllegalArgumentException("Marking/arc contains a foreign node");
        return i;
    }
    private void edge(int from, int to, int weight) {
        reserve(64L); outgoing.get(from).add(new Edge(to,weight)); incoming.get(to).add(new Edge(from,weight));
    }
    private static final class Edge {
        final int to, weight;
        Edge(int to,int weight) {this.to=to;this.weight=weight;}
    }
    private int[] compress(String[] signatures) {
        TreeMap<String,Integer> keys=new TreeMap<String,Integer>();
        for(String s:signatures) {check();keys.put(s,0);}
        int color=0; for(String s:keys.keySet()) {check();keys.put(s,color++);}
        reserve(32L+4L*signatures.length);
        int[] colors=new int[signatures.length];
        for(int i=0;i<colors.length;i++) {check();colors[i]=keys.get(signatures[i]);}
        return colors;
    }
    private int count(int[] colors) {
        int max=-1;for(int c:colors) {check();max=Math.max(max,c);}return max+1;
    }
    private String neighbors(List<Edge> edges,int[] colors) {
        List<String> parts=new ArrayList<String>();
        for(Edge e:edges) {check();parts.add(colors[e.to]+":"+e.weight);}
        Collections.sort(parts); String s=parts.toString();reserve(48L+2L*s.length());return s;
    }
    private int[] refine(int[] colors) {
        while(true) {
            int before=count(colors);
            String[] sig=new String[colors.length];reserve(32L+8L*sig.length);
            for(int i=0;i<sig.length;i++) {
                check();sig[i]=colors[i]+"|"+neighbors(incoming.get(i),colors)+"|"+neighbors(outgoing.get(i),colors);
                reserve(40L+2L*sig[i].length());
            }
            int[] next=compress(sig);
            if(count(next)==before) return next;
            colors=next;
        }
    }
    private void search(int[] input,int depth) {
        check();if(++visits>10000 || depth>256) throw new ReproducibilityException("REPRODUCIBILITY_ORDER_LIMIT");
        int[] colors=refine(input);
        TreeMap<Integer,List<Integer>> cells=new TreeMap<Integer,List<Integer>>();
        for(int i=0;i<colors.length;i++) {
            check();List<Integer> cell=cells.get(colors[i]);
            if(cell==null){cell=new ArrayList<Integer>();cells.put(colors[i],cell);}cell.add(i);
        }
        List<Integer> split=null;
        for(List<Integer> cell:cells.values()) if(cell.size()>1 && (split==null || cell.size()<split.size())) split=cell;
        if(split==null) {
            int[] order=new int[colors.length];for(int i=0;i<colors.length;i++) order[colors[i]]=i;
            String encoding=encode(order);
            if(best==null || encoding.compareTo(best)<0) {best=encoding;bestOrder=order;}
            return;
        }
        int newColor=count(colors);
        boolean twins=true;
        for(int k=1;k<split.size();k++) if(!twins(split.get(0),split.get(k))) {twins=false;break;}
        if(twins) {
            reserve(32L+4L*colors.length);int[] next=colors.clone();
            for(int v:split) next[v]=newColor++;
            search(next,depth+1);return;
        }
        // Exact search; no pruning solely because two refinement hashes match.
        for(int v:split) {
            reserve(32L+4L*colors.length);int[] next=colors.clone();next[v]=newColor;
            search(next,depth+1);
        }
    }
    private int swap(int v,int a,int b) {return v==a?b:v==b?a:v;}
    private boolean twins(int a,int b) {
        if(!labels.get(a).equals(labels.get(b))) return false;
        return swappedEdges(outgoing.get(a),outgoing.get(b),a,b)
            && swappedEdges(incoming.get(a),incoming.get(b),a,b);
    }
    private boolean swappedEdges(List<Edge> left,List<Edge> right,int a,int b) {
        if(left.size()!=right.size())return false;
        List<String> l=new ArrayList<String>(),r=new ArrayList<String>();
        for(Edge e:left){check();l.add(swap(e.to,a,b)+":"+e.weight);}
        for(Edge e:right){check();r.add(e.to+":"+e.weight);}
        Collections.sort(l);Collections.sort(r);return l.equals(r);
    }
    private String encode(int[] order) {
        int[] reverse=new int[order.length];for(int i=0;i<order.length;i++)reverse[order[i]]=i;
        StringBuilder b=new StringBuilder();
        for(int v:order) {
            check();String label=labels.get(v);b.append(label.length()).append(':').append(label).append('|');
            List<String> es=new ArrayList<String>();
            for(Edge e:outgoing.get(v)) {check();es.add(reverse[e.to]+":"+e.weight);}
            Collections.sort(es);b.append(es).append(';');
        }
        reserve(64L+2L*b.length());return b.toString();
    }
    public int index(PetrinetNode node) {return ranks.get(node);}
    public <N extends PetrinetNode> Comparator<N> comparator() {
        return new Comparator<N>() {public int compare(N a,N b){return Integer.compare(index(a),index(b));}};
    }
    public List<Place> places() {
        List<Place> out=new ArrayList<Place>();for(PetrinetNode n:nodes)if(n instanceof Place)out.add((Place)n);
        Collections.sort(out,this.<Place>comparator());return out;
    }
    public List<Transition> transitions() {
        List<Transition> out=new ArrayList<Transition>();for(PetrinetNode n:nodes)if(n instanceof Transition)out.add((Transition)n);
        Collections.sort(out,this.<Transition>comparator());return out;
    }
    public String markingKey(Marking m) {
        List<String> tokens=new ArrayList<String>();
        for(Place p:m.baseSet()) {ExecutionChecks.check();tokens.add(index(p)+":"+m.occurrences(p));}
        Collections.sort(tokens);return tokens.toString();
    }
    public String signature() {return best;}
    public String semanticHash() {
        try {
            byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(
                best.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder b=new StringBuilder();for(byte v:hash)b.append(String.format("%02x",v & 255));return b.toString();
        } catch(java.security.NoSuchAlgorithmException e) {throw new IllegalStateException(e);}
    }
}
