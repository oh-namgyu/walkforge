"""Acceptance checks over realistic, hand-written scenario specs.

These stand in for the question a reader actually asks of a walkthrough:
can I tell where I am and what I can choose? The deterministic proxy is
that each fixture validates cleanly, reads as prose, and carries the
initial state's name, description and choices into the rendered page.
"""

import json
import os
import re
import unittest
from typing import Any, Dict, List, Tuple

from walkforge.layout import compute_layout
from walkforge.renderer import render_spec
from walkforge.spec import load_spec, validate_spec

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SCENARIOS = ("scenario_incident.json", "scenario_onboarding.json", "scenario_decision.json")
DATA_BLOCK = re.compile(r'<script type="application/json" id="spec-data">(.*?)</script>', re.DOTALL)


def load(name: str) -> Dict[str, Any]:
    """Read one scenario fixture."""
    return load_spec(os.path.join(FIXTURES, name))


def embedded(document: str) -> Any:
    """Return the spec parsed back out of a rendered page."""
    found = DATA_BLOCK.search(document)
    assert found is not None, "no embedded spec block"
    return json.loads(found.group(1))


def outgoing(spec: Dict[str, Any], state_id: str) -> List[Dict[str, Any]]:
    """Return the transitions leaving one state, in declaration order."""
    return [move for move in spec["transitions"] if move["from"] == state_id]


def reachable(spec: Dict[str, Any]) -> List[str]:
    """Return every state id reachable from the initial state."""
    seen = [spec["initial"]]
    queue = [spec["initial"]]
    while queue:
        for move in outgoing(spec, queue.pop(0)):
            if move["to"] not in seen:
                seen.append(move["to"])
                queue.append(move["to"])
    return seen


class ScenarioTest(unittest.TestCase):
    """Every scenario must survive validation, layout and rendering."""

    def each(self) -> List[Tuple[str, Dict[str, Any]]]:
        return [(name, load(name)) for name in SCENARIOS]

    def test_every_scenario_validates_without_errors_or_warnings(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                result = validate_spec(spec)
                self.assertEqual([], result.errors)
                self.assertEqual([], result.warnings)

    def test_every_scenario_is_a_realistic_size(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                self.assertTrue(8 <= len(spec["states"]) <= 14, len(spec["states"]))
                branches = [
                    state for state in spec["states"] if len(outgoing(spec, state["id"])) > 1
                ]
                self.assertTrue(branches, "a walkthrough without a branch is a list")

    def test_an_end_state_is_reachable(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                arrived = reachable(spec)
                ends = [
                    state["id"]
                    for state in spec["states"]
                    if state.get("is_end") and state["id"] in arrived
                ]
                self.assertTrue(ends, "no end state can be reached")
                self.assertEqual(len(spec["states"]), len(arrived))

    def test_every_state_reads_as_prose(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                for state in spec["states"]:
                    self.assertTrue(state["name"].strip(), state["id"])
                    description = state["description"].strip()
                    self.assertTrue(description, state["id"])
                    self.assertGreater(len(description), 40, state["id"])
                    self.assertTrue(description.endswith("."), state["id"])

    def test_every_choice_reads_as_a_choice(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                for move in spec["transitions"]:
                    label = move["label"].strip()
                    self.assertTrue(label, move["from"])
                    self.assertLessEqual(len(label), 60, label)

    def test_the_page_carries_the_opening_step(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                document = render_spec(spec, compute_layout(spec))
                data = embedded(document)
                self.assertEqual(spec, data)
                start = [s for s in data["states"] if s["id"] == data["initial"]][0]
                self.assertIn(start["name"], json.dumps(data, ensure_ascii=True))
                self.assertIn(start["description"][:40], json.dumps(data, ensure_ascii=True))
                self.assertTrue(outgoing(data, data["initial"]))
                self.assertIn('id="choice-list"', document)

    def test_the_graph_draws_every_state_and_choice(self) -> None:
        for name, spec in self.each():
            with self.subTest(name):
                layout = compute_layout(spec)
                svg = re.search(r"<svg.*?</svg>", render_spec(spec, layout), re.DOTALL)
                assert svg is not None
                markup = svg.group(0)
                self.assertEqual(len(spec["states"]), markup.count('class="node"'))
                self.assertEqual(len(spec["transitions"]), markup.count("<polyline"))
                index = [s["id"] for s in spec["states"]].index(spec["initial"])
                self.assertIn('id="n%d"' % index, markup)
                self.assertIn('data-from="%d"' % index, markup)


if __name__ == "__main__":
    unittest.main()
