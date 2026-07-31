import os
import sys
import unittest


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from api.petri import _petri_from_pnml


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


if __name__ == "__main__":
    unittest.main()
