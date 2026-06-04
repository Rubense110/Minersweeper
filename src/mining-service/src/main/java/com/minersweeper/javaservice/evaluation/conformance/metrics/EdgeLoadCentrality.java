package com.minersweeper.javaservice.evaluation.conformance.metrics;

import com.minersweeper.javaservice.evaluation.conformance.ConformanceComputation;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.jgrapht.Graph;
import org.jgrapht.graph.DefaultEdge;
import org.jgrapht.graph.DirectedMultigraph;
import org.processmining.models.graphbased.directed.petrinet.Petrinet;
import org.processmining.models.graphbased.directed.petrinet.PetrinetEdge;
import org.processmining.models.graphbased.directed.petrinet.PetrinetNode;
import org.processmining.models.graphbased.directed.petrinet.elements.Place;
import org.processmining.models.graphbased.directed.petrinet.elements.Transition;

public class EdgeLoadCentrality implements ConformanceMetric {
    public static final String KEY = "elc";

    @Override
    public String key() {
        return KEY;
    }

    @Override
    public double compute(ConformanceComputation computation) {
        Petrinet net = computation.getNet();
        int edgeCount = net.getEdges().size();
        if (edgeCount == 0) {
            return 0.0;
        }

        Graph<PetrinetNode, DefaultEdge> graph = new DirectedMultigraph<PetrinetNode, DefaultEdge>(DefaultEdge.class);
        for (Place place : net.getPlaces()) {
            graph.addVertex(place);
        }
        for (Transition transition : net.getTransitions()) {
            graph.addVertex(transition);
        }
        for (PetrinetEdge<? extends PetrinetNode, ? extends PetrinetNode> edge : net.getEdges()) {
            graph.addEdge(edge.getSource(), edge.getTarget());
        }

        double[] scores = rawDirectedEdgeLoad(graph);

        double totalLoad = 0.0;
        for (double score : scores) {
            if (Double.isFinite(score)) {
                totalLoad += score;
            }
        }
        return totalLoad / edgeCount;
    }

    @Override
    public boolean boundedUnitInterval() {
        return false;
    }

    private double[] rawDirectedEdgeLoad(Graph<PetrinetNode, DefaultEdge> graph) {
        List<PetrinetNode> vertices = new ArrayList<PetrinetNode>(graph.vertexSet());
        List<DefaultEdge> edges = new ArrayList<DefaultEdge>(graph.edgeSet());
        int vertexCount = vertices.size();
        int edgeCount = edges.size();

        Map<PetrinetNode, Integer> vertexIndices = new HashMap<PetrinetNode, Integer>(vertexCount);
        for (int index = 0; index < vertexCount; index++) {
            vertexIndices.put(vertices.get(index), index);
        }

        int[] edgeSources = new int[edgeCount];
        int[] edgeTargets = new int[edgeCount];
        int[] outgoingCounts = new int[vertexCount];
        int[] incomingCounts = new int[vertexCount];
        for (int edgeIndex = 0; edgeIndex < edgeCount; edgeIndex++) {
            DefaultEdge edge = edges.get(edgeIndex);
            int source = vertexIndices.get(graph.getEdgeSource(edge)).intValue();
            int target = vertexIndices.get(graph.getEdgeTarget(edge)).intValue();
            edgeSources[edgeIndex] = source;
            edgeTargets[edgeIndex] = target;
            outgoingCounts[source]++;
            incomingCounts[target]++;
        }

        int[][] outgoingEdges = new int[vertexCount][];
        int[][] predecessorEdges = new int[vertexCount][];
        for (int vertex = 0; vertex < vertexCount; vertex++) {
            outgoingEdges[vertex] = new int[outgoingCounts[vertex]];
            predecessorEdges[vertex] = new int[incomingCounts[vertex]];
        }

        int[] outgoingPositions = new int[vertexCount];
        for (int edgeIndex = 0; edgeIndex < edgeCount; edgeIndex++) {
            int source = edgeSources[edgeIndex];
            outgoingEdges[source][outgoingPositions[source]++] = edgeIndex;
        }

        double[] scores = new double[edgeCount];
        int[] stack = new int[vertexCount];
        int[] queue = new int[vertexCount];
        int[] distance = new int[vertexCount];
        int[] predecessorCounts = new int[vertexCount];
        double[] pathCounts = new double[vertexCount];
        double[] dependency = new double[vertexCount];

        for (int source = 0; source < vertexCount; source++) {
            Arrays.fill(distance, -1);
            Arrays.fill(predecessorCounts, 0);
            Arrays.fill(pathCounts, 0.0);
            Arrays.fill(dependency, 0.0);

            int stackSize = 0;
            int queueHead = 0;
            int queueTail = 0;
            distance[source] = 0;
            pathCounts[source] = 1.0;
            queue[queueTail++] = source;

            while (queueHead < queueTail) {
                int vertex = queue[queueHead++];
                stack[stackSize++] = vertex;
                for (int edgePosition = 0; edgePosition < outgoingEdges[vertex].length; edgePosition++) {
                    int edgeIndex = outgoingEdges[vertex][edgePosition];
                    int target = edgeTargets[edgeIndex];
                    if (distance[target] < 0) {
                        distance[target] = distance[vertex] + 1;
                        queue[queueTail++] = target;
                    }
                    if (distance[target] == distance[vertex] + 1) {
                        pathCounts[target] += pathCounts[vertex];
                        predecessorEdges[target][predecessorCounts[target]++] = edgeIndex;
                    }
                }
            }

            while (stackSize > 0) {
                int target = stack[--stackSize];
                double targetPathCount = pathCounts[target];
                if (targetPathCount == 0.0) {
                    continue;
                }
                for (int predecessorPosition = 0; predecessorPosition < predecessorCounts[target]; predecessorPosition++) {
                    int edgeIndex = predecessorEdges[target][predecessorPosition];
                    int predecessor = edgeSources[edgeIndex];
                    double contribution = (pathCounts[predecessor] / targetPathCount) * (1.0 + dependency[target]);
                    scores[edgeIndex] += contribution;
                    dependency[predecessor] += contribution;
                }
            }
        }

        return scores;
    }
}
