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

// Modified for Minersweeper: deterministic merges; see vendor/splitminer/README.md.
package processmining.splitminer.oracle;

import com.minersweeper.javaservice.evaluation.ExecutionChecks;
import java.util.*;

public class Oracle {
  public Oracle() {}

  public OracleItem getFinalOracleItem(Set<OracleItem> input) {
    if (input.isEmpty()) throw new IllegalArgumentException("Oracle requires a successor");
    // Lists preserve distinct candidates, including equal signatures/hierarchies.
    List<OracleItem> items = new ArrayList<>(input);
    int forcedCount = 0;
    while (items.size() > 1) {
      ExecutionChecks.check();
      boolean merged = false;
      Set<OracleItem> group;
      // Preserve the original heuristic's XOR priority and distance measure.
      while (!(group = mergeable(items, true)).isEmpty()) {
        items.removeAll(group);
        items.add(OracleItem.mergeXORs(group));
        merged = true;
      }
      group = mergeable(items, false);
      if (!group.isEmpty()) {
        items.removeAll(group);
        items.add(OracleItem.mergeANDs(group));
        merged = true;
      }
      if (!merged) {
        List<OracleItem> ordered = OracleItem.stableOrder(items);
        int minimum = Integer.MAX_VALUE;
        OracleItem first = null, second = null;
        for (int i = 0; i < ordered.size(); i++) {
          ExecutionChecks.check();
          for (int j = i + 1; j < ordered.size(); j++) {
            int distance = ordered.get(i).getANDDistance(ordered.get(j));
            if (distance < minimum) {
              minimum = distance; first = ordered.get(i); second = ordered.get(j);
            }
          }
        }
        group = identitySet(); group.add(first); group.add(second);
        items.removeAll(group);
        items.add(OracleItem.forcedMergeANDs(group));
        forcedCount++;
      }
    }
    if (forcedCount > 0) System.out.println("DEBUG - forced AND merging: " + forcedCount);
    return items.get(0);
  }

  private Set<OracleItem> mergeable(List<OracleItem> items, boolean xor) {
    List<OracleItem> ordered = OracleItem.stableOrder(items);
    for (OracleItem first : ordered) {
      ExecutionChecks.check();
      Set<OracleItem> group = identitySet();
      for (OracleItem second : ordered)
        if (first != second && (xor ? first.isXOR(second) : first.isAND(second)))
          group.add(second);
      if (!group.isEmpty()) { group.add(first); return group; }
    }
    return identitySet();
  }

  private static Set<OracleItem> identitySet() {
    return Collections.newSetFromMap(new IdentityHashMap<OracleItem,Boolean>());
  }
}
