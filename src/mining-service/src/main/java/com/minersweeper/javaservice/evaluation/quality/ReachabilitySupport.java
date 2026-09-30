package com.minersweeper.javaservice.evaluation.quality;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Arc;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

/** Sparse weighted arcs and bounded work shared by our two reachability checks. */
public final class ReachabilitySupport {
    private ReachabilitySupport() {}
    public static final class Inconclusive extends RuntimeException {}

    public static final class Budget {
        final long deadline;
        long operations;
        long bytes;
        public int states;
        public boolean multipleComponents;
        public Budget(long nanos) { deadline = System.nanoTime() + nanos; }
        public void check() {
            ExecutionChecks.check();
            if (++operations > 4_000_000L || System.nanoTime() > deadline) throw new Inconclusive();
        }
        public void reserve(long amount) {
            check(); bytes += amount;
            if (bytes > 128L * 1024L * 1024L) throw new Inconclusive();
        }
    }

    public static final class StateKey {
        public final int[] tokens;
        private final int hash;
        public StateKey(int[] tokens) { this.tokens = tokens; hash = Arrays.hashCode(tokens); }
        @Override public int hashCode() { return hash; }
        @Override public boolean equals(Object other) {
            return other instanceof StateKey && Arrays.equals(tokens, ((StateKey) other).tokens);
        }
    }

    public static final class SparseNet {
        private final int[][] consume;
        private final int[][] produce;
        private final Budget budget;
        public SparseNet(Petrinet net, List<Place> places, List<Transition> transitions, Budget budget) {
            this.budget = budget;
            budget.reserve(32L * transitions.size() + 64L * places.size());
            Map<Place, Integer> indexes = new LinkedHashMap<Place, Integer>();
            for (Place place : places) { budget.check(); indexes.put(place, indexes.size()); }
            consume = new int[transitions.size()][]; produce = new int[transitions.size()][];
            for (int i = 0; i < transitions.size(); i++) {
                budget.check();
                consume[i] = arcs(net.getInEdges(transitions.get(i)), indexes, true);
                produce[i] = arcs(net.getOutEdges(transitions.get(i)), indexes, false);
            }
        }
        private int[] arcs(Iterable<? extends PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode>> edges,
            Map<Place, Integer> indexes, boolean input) {
            Map<Integer, Integer> weights = new LinkedHashMap<Integer, Integer>();
            for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : edges) {
                budget.check();
                PetrinetNode node = input ? edge.getSource() : edge.getTarget();
                if (!(edge instanceof Arc) || !(node instanceof Place)) throw new Inconclusive();
                Integer index = indexes.get(node);
                if (index == null) throw new Inconclusive();
                int weight = ((Arc) edge).getWeight();
                Integer previous = weights.get(index);
                weights.put(index, Math.addExact(previous == null ? 0 : previous, weight));
            }
            budget.reserve(32L + 8L * weights.size());
            int[] result = new int[2 * weights.size()]; int index = 0;
            for (Map.Entry<Integer, Integer> entry : weights.entrySet()) {
                result[index++] = entry.getKey(); result[index++] = entry.getValue();
            }
            return result;
        }
        public boolean enabled(int transition, int[] state) {
            budget.check();
            int[] arcs = consume[transition];
            for (int i = 0; i < arcs.length; i += 2) {
                budget.check(); if (state[arcs[i]] < arcs[i + 1]) return false;
            }
            return true;
        }
        public int[] fire(int transition, int[] state) {
            budget.reserve(32L + 4L * state.length);
            int[] next = state.clone();
            for (int i = 0; i < consume[transition].length; i += 2) {
                budget.check(); next[consume[transition][i]] -= consume[transition][i + 1];
            }
            for (int i = 0; i < produce[transition].length; i += 2) {
                budget.check(); next[produce[transition][i]] = Math.addExact(next[produce[transition][i]], produce[transition][i + 1]);
            }
            return next;
        }
    }
}
