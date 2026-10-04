"""NSGA-III 1.9.0 adapter with an instance-owned niching RNG.

Replacement/niching adapted from jMetalPy (Antonio J. Nebro et al., MIT).
Keep ranking, normalization and constraint dominance identical to the pinned
upstream version; only random draws are redirected to a private Generator.

MIT License

Copyright (c) 2018 Antonio J. Nebro

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

import numpy as np
from jmetal.algorithm.multiobjective.nsgaiii import (
    NSGAIII, associate_to_niches, compute_niche_count,
    get_extreme_points, get_nadir_point,
)
from jmetal.util.ranking import FastNonDominatedRanking

RNG_POLICY_VERSION = "minersweeper-rng-v1"

def seeded_niching(pop, n_remaining, niche_count, niche_of_individuals, dist_to_niche, rng):
    survivors = []

    # boolean array of elements that are considered for each iteration
    mask = np.full(len(pop), True)

    while len(survivors) < n_remaining:
        # number of individuals to select in this iteration
        n_select = n_remaining - len(survivors)

        # all niches where new individuals can be assigned to and the corresponding niche count
        next_niches_list = np.unique(niche_of_individuals[mask])
        next_niche_count = niche_count[next_niches_list]

        # the minimum niche count
        min_niche_count = next_niche_count.min()

        # all niches with the minimum niche count (truncate if randomly select more niches than remaining individuals)
        next_niches = next_niches_list[np.where(next_niche_count == min_niche_count)[0]]
        next_niches = next_niches[rng.permutation(len(next_niches))[:n_select]]

        for next_niche in next_niches:
            # indices of individuals that are considered and assign to next_niche
            next_ind = np.where(np.logical_and(niche_of_individuals == next_niche, mask))[0]

            # shuffle to break random_search tie (equal perp. dist) or select randomly
            rng.shuffle(next_ind)

            if niche_count[next_niche] == 0:
                next_ind = next_ind[np.argmin(dist_to_niche[next_ind])]
                is_closest = True
            else:
                # already randomized through shuffling
                next_ind = next_ind[0]
                is_closest = False

            # add the selected individual to the survivors
            mask[next_ind] = False
            pop[next_ind].attributes["is_closest"] = is_closest
            survivors.append(int(next_ind))

            # increase the corresponding niche count
            niche_count[next_niche] += 1

    return survivors

class SeededNSGAIII(NSGAIII):
    def __init__(self, *args, niching_rng, **kwargs):
        super().__init__(*args, **kwargs)
        self.niching_rng = niching_rng

    def replacement(self, population, offspring_population):
        """Implements NSGA-III environmental selection based on reference points as described in:

        * Deb, K., & Jain, H. (2014). An Evolutionary Many-Objective Optimization
          Algorithm Using Reference-Point-Based Nondominated Sorting Approach,
          Part I: Solving Problems With Box Constraints. IEEE Transactions on
          Evolutionary Computation, 18(4), 577–601. doi:10.1109/TEVC.2013.2281535.
        """
        F = np.array([s.objectives for s in population])

        # find or usually update the new ideal point - from feasible solutions
        # note that we are assuming minimization here!
        self.ideal_point = np.min(np.vstack((self.ideal_point, F)), axis=0)
        self.worst_point = np.max(np.vstack((self.worst_point, F)), axis=0)

        # calculate the fronts of the population
        ranking = FastNonDominatedRanking(self.dominance_comparator)
        ranking.compute_ranking(population + offspring_population, k=self.population_size)

        fronts, non_dominated = ranking.ranked_sublists, ranking.get_subfront(0)

        # find the extreme points for normalization
        self.extreme_points = get_extreme_points(
            F=np.array([s.objectives for s in non_dominated]),
            n_objs=self.problem.number_of_objectives(),
            ideal_point=self.ideal_point,
            extreme_points=self.extreme_points,
        )

        # find the intercepts for normalization and do backup if gaussian elimination fails
        worst_of_population = np.max(F, axis=0)
        worst_of_front = np.max(np.array([s.objectives for s in non_dominated]), axis=0)

        nadir_point = get_nadir_point(
            extreme_points=self.extreme_points,
            ideal_point=self.ideal_point,
            worst_point=self.worst_point,
            worst_of_population=worst_of_population,
            worst_of_front=worst_of_front,
        )

        #  consider only the population until we come to the splitting front
        pop = np.concatenate(ranking.ranked_sublists)
        F = np.array([s.objectives for s in pop])

        # update the front indices for the current population
        counter = 0
        for i in range(len(fronts)):
            for j in range(len(fronts[i])):
                fronts[i][j] = counter
                counter += 1
        last_front = np.array(fronts[-1])

        # associate individuals to niches
        niche_of_individuals, dist_to_niche = associate_to_niches(
            F=F, niches=self.reference_directions, ideal_point=self.ideal_point, nadir_point=nadir_point
        )

        # if we need to select individuals to survive
        if len(pop) > self.population_size:
            # if there is only one front
            if len(fronts) == 1:
                until_last_front = np.array([], dtype=int)
                niche_count = np.zeros(len(self.reference_directions), dtype=int)
                n_remaining = self.population_size
            # if some individuals already survived
            else:
                until_last_front = np.concatenate(fronts[:-1])
                niche_count = compute_niche_count(
                    len(self.reference_directions), niche_of_individuals[until_last_front]
                )
                n_remaining = self.population_size - len(until_last_front)

            S_idx = seeded_niching(
                rng=self.niching_rng,
                pop=pop[last_front],
                n_remaining=n_remaining,
                niche_count=niche_count,
                niche_of_individuals=niche_of_individuals[last_front],
                dist_to_niche=dist_to_niche[last_front],
            )

            survivors_idx = np.concatenate((until_last_front, last_front[S_idx].tolist()))
            pop = pop[survivors_idx]

        return list(pop)
