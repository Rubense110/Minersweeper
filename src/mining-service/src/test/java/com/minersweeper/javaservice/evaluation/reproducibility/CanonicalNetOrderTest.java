package com.minersweeper.javaservice.evaluation.reproducibility;

import static org.junit.Assert.*;
import java.util.*;
import org.junit.Test;
import com.minersweeper.javaservice.evaluation.*;
import com.minersweeper.javaservice.evaluation.conformance.*;
import com.minersweeper.javaservice.evaluation.quality.ModelQualityAnalyzer;
import org.deckfour.xes.extension.std.XConceptExtension;
import org.deckfour.xes.factory.XFactoryNaiveImpl;
import org.deckfour.xes.model.*;
import org.processmining.models.graphbased.directed.petrinet.*;
import org.processmining.models.graphbased.directed.petrinet.elements.*;
import org.processmining.models.graphbased.directed.petrinet.impl.PetrinetFactory;
import org.processmining.models.semantics.petrinet.Marking;

public class CanonicalNetOrderTest {
    static final class Model {
        final Petrinet net=PetrinetFactory.newPetrinet("ignored");
        final Marking initial=new Marking(),fin=new Marking();
    }
    private static Model choice(int seed, boolean hidden) {
        Model m=new Model();Random rng=new Random(seed);
        List<Integer> creation=new ArrayList<Integer>(Arrays.asList(0,1,2,3,4,5));Collections.shuffle(creation,rng);
        Place[] p=new Place[6];for(int i:creation)p[i]=m.net.addPlace("generated-"+rng.nextInt());
        List<String> labels=new ArrayList<String>(Arrays.asList("A","A","B","B","C"));
        List<Integer> ti=new ArrayList<Integer>(Arrays.asList(0,1,2,3,4));Collections.shuffle(ti,rng);
        Transition[] t=new Transition[5];for(int i:ti)t[i]=m.net.addTransition(labels.get(i));
        m.net.addArc(p[0],t[0]);m.net.addArc(t[0],p[1]);m.net.addArc(p[0],t[1]);m.net.addArc(t[1],p[2]);
        m.net.addArc(p[1],t[2]);m.net.addArc(t[2],p[5]);
        if(hidden){Transition tau=m.net.addTransition("random-tau-"+rng.nextInt());tau.setInvisible(true);
            m.net.addArc(p[2],tau);m.net.addArc(tau,p[3]);m.net.addArc(p[3],t[4]);}
        else m.net.addArc(p[2],t[4]);
        m.net.addArc(t[4],p[4]);m.net.addArc(p[4],t[3]);m.net.addArc(t[3],p[5]);
        // Remove the unused place so both variants have one connected component.
        if(!hidden)m.net.removePlace(p[3]);
        m.initial.add(p[0]);m.fin.add(p[5]);return m;
    }
    @Test public void duplicateLabelsReplayAndQualityAreStableUnderFreshIdsAndConstructionOrders() throws Exception {
        for(boolean hidden:new boolean[]{false,true}) {
            String expected=null;Double fitness=null;Map<String,Double> expectedMetrics=null;
            for(int seed=0;seed<40;seed++) {
                Model m=choice(seed,hidden);
                CanonicalNetOrder order=new CanonicalNetOrder(m.net,m.initial,Arrays.asList(m.fin));
                if(expected==null)expected=order.semanticHash();assertEquals(expected,order.semanticHash());
                ModelQualityAnalyzer.Result q=new ModelQualityAnalyzer().analyze(m.net,m.initial,Arrays.asList(m.fin));
                assertTrue(q.violations().toString(),q.violations().isEmpty());assertEquals(expected,q.modelSemanticHash);
                TokenReplayResult r=ConformanceComputation.withFinalMarkings(null,log("A","B"),m.net,m.initial,
                    Arrays.asList(m.fin),ConformanceMode.REPLAY_TOKEN,null).getTokenReplayResult();
                if(fitness==null)fitness=r.fitness();assertEquals(fitness.doubleValue(),r.fitness(),0.0);
                Map<String,Double> metrics=new ConformanceMetricsCalculator().compute(null,log("A","B"),m.net,
                    m.initial,Arrays.asList(m.fin),Arrays.asList("fitness","precision","simplicity","generalisation","elc"),
                    ConformanceMode.REPLAY_TOKEN,null,null,"probe","probe");
                if(expectedMetrics==null)expectedMetrics=metrics;assertEquals(expectedMetrics,metrics);
            }
        }
    }
    @Test public void refinementTiesDoNotConflateNonIsomorphicRegularGraphs() {
        assertNotEquals(cycles(4).signature(),cycles(2,2).signature());
        assertEquals(cycles(4).signature(),cycles(4).signature());
    }
    @Test public void generatedWeightedGraphsAndCorrelatedMarkingsIgnoreAllConstructionOrders() {
        // Generate one graph specification, then instantiate it with fresh UUIDs,
        // permuted vertices/arcs/accepting markings and arbitrary internal names.
        for(int specification=0;specification<40;specification++) {
            Random shape=new Random(specification);
            int places=5,transitions=4;
            int[][] before=new int[places][transitions],after=new int[places][transitions];
            for(int p=0;p<places;p++)for(int t=0;t<transitions;t++) {
                if(shape.nextBoolean())before[p][t]=1+shape.nextInt(3);
                if(shape.nextBoolean())after[p][t]=1+shape.nextInt(3);
            }
            String expected=null;
            for(int permutation=0;permutation<16;permutation++) {
                Random construction=new Random(permutation);Model model=new Model();
                List<Integer> pi=new ArrayList<>(Arrays.asList(0,1,2,3,4));
                List<Integer> ti=new ArrayList<>(Arrays.asList(0,1,2,3));
                Collections.shuffle(pi,construction);Collections.shuffle(ti,construction);
                Place[] p=new Place[places];Transition[] t=new Transition[transitions];
                for(int index:pi)p[index]=model.net.addPlace("internal-"+construction.nextInt());
                for(int index:ti) {
                    t[index]=model.net.addTransition(index==0?"tau-"+construction.nextInt():"visible-"+(index%2));
                    t[index].setInvisible(index==0);
                }
                for(int i:pi)for(int j:ti) {
                    if(before[i][j]>0)model.net.addArc(p[i],t[j],before[i][j]);
                    if(after[i][j]>0)model.net.addArc(t[j],p[i],after[i][j]);
                }
                model.initial.add(p[0],2);model.fin.add(p[4],2);model.fin.add(p[1]);
                Marking other=new Marking();other.add(p[2],3);other.add(p[3]);
                List<Marking> finals=new ArrayList<>(Arrays.asList(model.fin,other));
                Collections.shuffle(finals,construction);
                String actual=new CanonicalNetOrder(model.net,model.initial,finals).semanticHash();
                if(expected==null)expected=actual;
                assertEquals("graph="+specification+", permutation="+permutation,expected,actual);
            }
        }
    }
    private static CanonicalNetOrder cycles(int... sizes) {
        Petrinet n=PetrinetFactory.newPetrinet("cycle");
        for(int size:sizes) {
            Place[] p=new Place[size];Transition[] t=new Transition[size];
            for(int i=0;i<size;i++){p[i]=n.addPlace("");t[i]=n.addTransition("A");}
            for(int i=0;i<size;i++){n.addArc(p[i],t[i]);n.addArc(t[i],p[(i+1)%size]);}
        }
        return new CanonicalNetOrder(n,new Marking(),Collections.<Marking>emptyList());
    }
    @Test public void trueTwinsArePrunedWithoutFactorialSearch() {
        Petrinet n=PetrinetFactory.newPetrinet("twins");for(int i=0;i<40;i++)n.addPlace("");
        assertEquals(new CanonicalNetOrder(n,new Marking(),Collections.<Marking>emptyList()).signature(),
                     new CanonicalNetOrder(n,new Marking(),Collections.<Marking>emptyList()).signature());
    }
    @Test public void weightsAndAcceptanceArePartOfTheHash() {
        Model m=choice(1,false);String hash=new CanonicalNetOrder(m.net,m.initial,Arrays.asList(m.fin)).semanticHash();
        Marking other=new Marking();assertNotEquals(hash,new CanonicalNetOrder(m.net,other,Arrays.asList(m.fin)).semanticHash());
        Arc a=(Arc)m.net.getEdges().iterator().next();a.setWeight(2);
        assertNotEquals(hash,new CanonicalNetOrder(m.net,m.initial,Arrays.asList(m.fin)).semanticHash());
    }
    @Test public void finalCollectionOrderDoesNotChangeTheHash() {
        Model m=choice(3,false);Marking another=new Marking(m.initial);
        assertEquals(new CanonicalNetOrder(m.net,m.initial,Arrays.asList(m.fin,another)).semanticHash(),
                     new CanonicalNetOrder(m.net,m.initial,Arrays.asList(another,m.fin)).semanticHash());
    }
    @Test public void exhaustedOrderingBudgetNeverFallsBackToUuid() {
        Model m=choice(0,false);
        try {new CanonicalNetOrder(m.net,m.initial,Arrays.asList(m.fin),1L);fail();}
        catch(ReproducibilityException e){assertEquals("REPRODUCIBILITY_ORDER_LIMIT",e.code);}
    }
    @Test public void timeCutoffIsNotAnAlternativeQualityResultAndScopeIsReleased() {
        Model m=choice(0,false);
        try {new ModelQualityAnalyzer(5000,10,1L).analyze(m.net,m.initial,Arrays.asList(m.fin));fail();}
        catch(ReproducibilityException e){assertEquals("REPRODUCIBILITY_TIME_LIMIT",e.code);}
        ExecutionChecks.check();
        assertTrue(new ModelQualityAnalyzer().analyze(m.net,m.initial,Arrays.asList(m.fin)).violations().isEmpty());
    }
    @Test public void workLimitAndTimeLimitAreDifferentAndScopesRestoreTheirParent() {
        try(ExecutionChecks.Work ignored=ExecutionChecks.withinWork(1L)) {
            ExecutionChecks.check();try{ExecutionChecks.check();fail();}catch(ExecutionChecks.WorkLimitExceeded expected){}
        }
        ExecutionChecks.check();
        try(ExecutionChecks.Deadline ignored=ExecutionChecks.within(1L)) {
            try{ExecutionChecks.check();fail();}catch(ExecutionChecks.DeadlineExceeded expected){}
        }
        ExecutionChecks.check();
    }
    private static XLog log(String... activities) {
        XFactoryNaiveImpl f=new XFactoryNaiveImpl();XLog l=f.createLog();XTrace t=f.createTrace();
        for(String a:activities){XEvent e=f.createEvent();XConceptExtension.instance().assignName(e,a);t.add(e);}l.add(t);return l;
    }
}
