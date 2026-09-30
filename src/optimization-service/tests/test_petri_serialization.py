import os
import sys
import unittest


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from api.petri import _petri_from_pnml, _petri_from_v2_artifact


class PetriPnmlSerializationTest(unittest.TestCase):
    def test_petri_from_pnml_extracts_markings_and_invisibility(self):
        pnml = """
        <pnml>
          <net id="n1">
            <place id="p_start">
              <name><text>start</text></name>
              <initialMarking><text>1</text></initialMarking>
            </place>
            <place id="p_end">
              <name><text>end</text></name>
              <finalMarking><text>1</text></finalMarking>
            </place>
            <transition id="t_visible">
              <name><text>A</text></name>
            </transition>
            <transition id="t_tau">
              <name><text>tau split</text></name>
            </transition>
            <transition id="t_hidden">
              <name><text>generated label</text></name>
              <toolspecific>
                <invisible>true</invisible>
              </toolspecific>
            </transition>
            <arc id="a1" source="p_start" target="t_visible" />
            <arc id="a2" source="t_visible" target="p_end" />
          </net>
        </pnml>
        """

        places, transitions, arcs, initial_marking, final_markings = _petri_from_pnml(pnml)

        self.assertEqual(
            [{"id": "p_start", "label": "start"}, {"id": "p_end", "label": "end"}],
            places,
        )
        self.assertEqual(
            [
                {"id": "t_visible", "label": "A", "is_invisible": False},
                {"id": "t_tau", "label": "tau split", "is_invisible": True},
                {"id": "t_hidden", "label": "generated label", "is_invisible": True},
            ],
            transitions,
        )
        self.assertEqual(
            [
                {"id": "a1", "source": "p_start", "target": "t_visible"},
                {"id": "a2", "source": "t_visible", "target": "p_end"},
            ],
            arcs,
        )
        self.assertEqual([{"place_id": "p_start", "tokens": 1}], initial_marking)
        self.assertEqual([[{"place_id": "p_end", "tokens": 1}]], final_markings)

    def test_petri_from_pnml_infers_missing_markings_from_source_and_sink_places(self):
        pnml = """
        <pnml>
          <net id="n1">
            <place id="p_start" />
            <place id="p_middle" />
            <place id="p_end" />
            <transition id="t1"><name><text>A</text></name></transition>
            <transition id="t2"><name><text>B</text></name></transition>
            <arc id="a1" source="p_start" target="t1" />
            <arc id="a2" source="t1" target="p_middle" />
            <arc id="a3" source="p_middle" target="t2" />
            <arc id="a4" source="t2" target="p_end" />
          </net>
        </pnml>
        """

        _places, _transitions, _arcs, initial_marking, final_markings = _petri_from_pnml(pnml)

        self.assertEqual([{"place_id": "p_start", "tokens": 1}], initial_marking)
        self.assertEqual([[{"place_id": "p_end", "tokens": 1}]], final_markings)

    def test_v2_artifact_preserves_real_markings_and_semantic_invisibility(self):
        artifact = {
            "model_schema_version": 2,
            "pnml": """
                <pnml><net id="n1">
                  <place id="p0"/><place id="p1"/>
                  <transition id="t_tau"><name><text>not authoritative</text></name></transition>
                  <transition id="t_hidden"><name><text>also not authoritative</text></name></transition>
                  <arc id="a1" source="p0" target="t_tau"/><arc id="a2" source="t_tau" target="p1"/>
                </net></pnml>
            """,
            "initial_marking": [{"place_id": "p0", "tokens": 3}, {"place_id": "p1", "tokens": 2}],
            "final_marking": [{"place_id": "p1", "tokens": 4}],
            "final_markings": [[{"place_id": "p1", "tokens": 4}], []],
            "transitions": [
                {"id": "t_tau", "label": "tau", "invisible": False},
                {"id": "t_hidden", "label": "arbitrary internal label", "invisible": True},
            ],
            "visible_transition_count": 1,
            "is_feasible": True,
            "constraint_violations": [],
        }

        places, transitions, _arcs, initial, final, finals = _petri_from_v2_artifact(artifact)

        self.assertEqual({"p0", "p1"}, {place["id"] for place in places})
        self.assertEqual(artifact["initial_marking"], initial)
        self.assertEqual(artifact["final_marking"], final)
        self.assertEqual(artifact["final_markings"], finals)
        self.assertEqual(
            [
                {"id": "t_tau", "label": "tau", "invisible": False},
                {"id": "t_hidden", "label": "arbitrary internal label", "invisible": True},
            ],
            transitions,
        )

    def test_v2_artifact_does_not_fall_back_to_topology_or_labels(self):
        artifact = {
            "model_schema_version": 2,
            "pnml": """
                <pnml><net id="n1"><place id="source"/><place id="sink"/>
                <transition id="t"><name><text>tau</text></name></transition>
                <arc id="a1" source="source" target="t"/><arc id="a2" source="t" target="sink"/>
                </net></pnml>
            """,
            "initial_marking": [],
            "final_marking": [],
            "final_markings": [[]],
            "transitions": [{"id": "t", "label": "tau", "invisible": False}],
            "visible_transition_count": 1,
            "is_feasible": True,
            "constraint_violations": [],
        }

        _places, transitions, _arcs, initial, final, finals = _petri_from_v2_artifact(artifact)
        self.assertEqual([], initial)
        self.assertEqual([], final)
        self.assertEqual([[]], finals)
        self.assertEqual(False, transitions[0]["invisible"])
        with self.assertRaisesRegex(ValueError, "missing semantic fields"):
            _petri_from_v2_artifact({"model_schema_version": 2, "pnml": artifact["pnml"]})

    def test_v2_artifact_rejects_visible_count_that_disagrees_with_transitions(self):
        artifact = self._minimal_v2_artifact()
        artifact["visible_transition_count"] = 1
        artifact["is_feasible"] = True
        artifact["constraint_violations"] = []

        with self.assertRaisesRegex(ValueError, "visible_transition_count does not match transitions"):
            _petri_from_v2_artifact(artifact)

    def test_v2_artifact_rejects_feasibility_that_disagrees_with_visible_count(self):
        artifact = self._minimal_v2_artifact()
        artifact["is_feasible"] = True
        artifact["constraint_violations"] = []

        with self.assertRaisesRegex(ValueError, "is_feasible does not match visible_transition_count"):
            _petri_from_v2_artifact(artifact)

    def test_v3_artifact_preserves_and_excludes_multiple_final_markings(self):
        artifact = {
            "model_schema_version": 3,
            "pnml": "<pnml><net><place id='p0'/><place id='p1'/><place id='p2'/><transition id='t'/></net></pnml>",
            "initial_marking": [{"place_id": "p0", "tokens": 1}],
            "final_marking": [{"place_id": "p1", "tokens": 1}],
            "final_markings": [[{"place_id": "p1", "tokens": 1}], [{"place_id": "p2", "tokens": 1}]],
            "transitions": [{"id": "t", "label": "A", "invisible": False}],
            "visible_transition_count": 1,
            "is_feasible": False,
            "constraint_violations": ["MULTIPLE_FINAL_MARKINGS"],
        }
        self.assertEqual(2, len(_petri_from_v2_artifact(artifact)[-1]))
        artifact["constraint_violations"] = []
        artifact["is_feasible"] = True
        with self.assertRaisesRegex(ValueError, "MULTIPLE_FINAL_MARKINGS"):
            _petri_from_v2_artifact(artifact)

    def test_v3_artifact_accepts_structural_exclusion_with_visible_transition(self):
        artifact = self._minimal_v2_artifact()
        artifact.update({
            "model_schema_version": 3,
            "transitions": [{"id": "t", "label": "A", "invisible": False}],
            "visible_transition_count": 1,
            "is_feasible": False,
            "constraint_violations": ["FINAL_NOT_REACHABLE"],
        })
        self.assertEqual(1, len(_petri_from_v2_artifact(artifact)[-1]))

    @staticmethod
    def _minimal_v2_artifact():
        return {
            "model_schema_version": 2,
            "pnml": "<pnml><net><place id='p0'/><place id='p1'/><transition id='t'/></net></pnml>",
            "initial_marking": [],
            "final_marking": [],
            "final_markings": [[]],
            "transitions": [{"id": "t", "label": "internal", "invisible": True}],
            "visible_transition_count": 0,
            "is_feasible": False,
            "constraint_violations": ["NO_VISIBLE_TRANSITIONS"],
        }


if __name__ == "__main__":
    unittest.main()
