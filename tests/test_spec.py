"""Tests for the structural (layer A) and graph (layer B) spec rules."""

import json
import os
import tempfile
import unittest
from typing import Any, Dict, List, Set

from walkforge.spec import SpecError, ValidationResult, load_spec, load_schema, validate_spec

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def base_spec() -> Dict[str, Any]:
    """A small spec that passes every rule with no warnings."""
    return {
        "title": "Base walkthrough",
        "initial": "start",
        "states": [
            {"id": "start", "name": "Start", "description": "First step."},
            {"id": "middle", "name": "Middle", "description": "Second step."},
            {"id": "done", "name": "Done", "description": "Last step.", "is_end": True},
        ],
        "transitions": [
            {"from": "start", "to": "middle", "label": "Go on"},
            {"from": "middle", "to": "done", "label": "Finish"},
        ],
    }


def state(state_id: str, is_end: bool = False) -> Dict[str, Any]:
    """Build a valid state entry."""
    entry: Dict[str, Any] = {
        "id": state_id,
        "name": state_id.replace("_", " ").title(),
        "description": "Step %s." % state_id,
    }
    if is_end:
        entry["is_end"] = True
    return entry


def transition(source: str, target: str, label: str = "Continue") -> Dict[str, Any]:
    """Build a valid transition entry."""
    return {"from": source, "to": target, "label": label}


def codes(messages: List[str]) -> Set[str]:
    """Return the rule codes carried by a list of messages."""
    return set(message.split(":", 1)[0] for message in messages)


class GraphRuleTest(unittest.TestCase):
    """Positive and negative case for every graph rule E1-E8 and W1."""

    def check(self, spec: Dict[str, Any]) -> ValidationResult:
        return validate_spec(spec)

    def test_base_spec_is_clean(self) -> None:
        result = self.check(base_spec())
        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)
        self.assertTrue(result.ok)

    def test_e1_unknown_initial(self) -> None:
        spec = base_spec()
        spec["initial"] = "ghost"
        self.assertIn("E1", codes(self.check(spec).errors))
        self.assertNotIn("E1", codes(self.check(base_spec()).errors))

    def test_e2_unknown_transition_endpoint(self) -> None:
        spec = base_spec()
        spec["transitions"].append(transition("middle", "ghost", "Detour"))
        self.assertIn("E2", codes(self.check(spec).errors))
        self.assertNotIn("E2", codes(self.check(base_spec()).errors))

    def test_e3_duplicate_state_id(self) -> None:
        spec = base_spec()
        spec["states"].append(state("middle"))
        self.assertIn("E3", codes(self.check(spec).errors))
        self.assertNotIn("E3", codes(self.check(base_spec()).errors))

    def test_e4_duplicate_label_from_same_state(self) -> None:
        spec = base_spec()
        spec["transitions"].append(transition("start", "done", "Go on"))
        self.assertIn("E4", codes(self.check(spec).errors))
        spec = base_spec()
        spec["transitions"].append(transition("start", "done", "Skip ahead"))
        self.assertNotIn("E4", codes(self.check(spec).errors))

    def test_e5_self_loop(self) -> None:
        spec = base_spec()
        spec["transitions"].append(transition("middle", "middle", "Repeat"))
        self.assertIn("E5", codes(self.check(spec).errors))
        self.assertNotIn("E5", codes(self.check(base_spec()).errors))

    def test_e6_dead_end_state(self) -> None:
        spec = base_spec()
        spec["states"].append(state("island"))
        result = self.check(spec)
        self.assertIn("E6", codes(result.errors))
        self.assertNotIn("E6", codes(self.check(base_spec()).errors))

    def test_e6_ignores_end_states_without_transitions(self) -> None:
        self.assertNotIn("E6", codes(self.check(base_spec()).errors))

    def test_e7_no_reachable_end_state(self) -> None:
        spec = base_spec()
        spec["states"] = [state("start"), state("middle")]
        spec["transitions"] = [
            transition("start", "middle", "Go on"),
            transition("middle", "start", "Back"),
        ]
        self.assertIn("E7", codes(self.check(spec).errors))
        self.assertNotIn("E7", codes(self.check(base_spec()).errors))

    def test_e8_trapped_cycle(self) -> None:
        spec = base_spec()
        spec["states"].extend([state("loop_a"), state("loop_b")])
        spec["transitions"].extend(
            [
                transition("middle", "loop_a", "Detour"),
                transition("loop_a", "loop_b", "Onward"),
                transition("loop_b", "loop_a", "Back"),
            ]
        )
        result = self.check(spec)
        self.assertIn("E8", codes(result.errors))
        self.assertNotIn("E6", codes(result.errors))
        self.assertNotIn("E8", codes(self.check(base_spec()).errors))

    def test_w1_unreachable_state_is_a_warning(self) -> None:
        spec = base_spec()
        spec["states"].append(state("island", is_end=True))
        result = self.check(spec)
        self.assertEqual([], result.errors)
        self.assertIn("W1", codes(result.warnings))
        self.assertTrue(result.ok)
        self.assertEqual([], self.check(base_spec()).warnings)

    def test_end_state_may_have_outgoing_transitions(self) -> None:
        spec = base_spec()
        spec["transitions"].append(transition("done", "start", "Start over"))
        self.assertEqual([], self.check(spec).errors)


class StructuralRuleTest(unittest.TestCase):
    """Layer A: rules driven by spec_schema.json."""

    def assert_structural(self, spec: Any) -> List[str]:
        errors = validate_spec(spec).errors
        self.assertTrue(errors, "expected a structural failure")
        self.assertEqual({"S"}, codes(errors))
        return errors

    def test_schema_declares_version(self) -> None:
        schema = load_schema()
        self.assertEqual(1, schema["version"])
        self.assertEqual("object", schema["type"])

    def test_wrong_root_type(self) -> None:
        self.assert_structural(["not", "an", "object"])

    def test_wrong_field_type(self) -> None:
        spec = base_spec()
        spec["title"] = 42
        self.assert_structural(spec)

    def test_boolean_field_rejects_string(self) -> None:
        spec = base_spec()
        spec["states"][2]["is_end"] = "yes"
        self.assert_structural(spec)

    def test_missing_required_field(self) -> None:
        spec = base_spec()
        del spec["initial"]
        self.assert_structural(spec)

    def test_missing_required_field_in_state(self) -> None:
        spec = base_spec()
        del spec["states"][0]["description"]
        self.assert_structural(spec)

    def test_state_id_pattern(self) -> None:
        spec = base_spec()
        spec["states"][0]["id"] = "Start Here"
        errors = self.assert_structural(spec)
        self.assertIn("states[0].id", errors[0])

    def test_string_too_long(self) -> None:
        spec = base_spec()
        spec["title"] = "t" * 121
        self.assert_structural(spec)

    def test_string_too_short(self) -> None:
        spec = base_spec()
        spec["states"][0]["name"] = ""
        self.assert_structural(spec)

    def test_empty_states_array(self) -> None:
        spec = base_spec()
        spec["states"] = []
        spec["transitions"] = []
        self.assert_structural(spec)

    def test_too_many_states(self) -> None:
        spec = base_spec()
        spec["states"] = [state("s%d" % index) for index in range(51)]
        self.assert_structural(spec)

    def test_additional_property_at_root(self) -> None:
        spec = base_spec()
        spec["colour"] = "blue"
        self.assert_structural(spec)

    def test_additional_property_in_state(self) -> None:
        spec = base_spec()
        spec["states"][0]["colour"] = "blue"
        self.assert_structural(spec)

    def test_additional_property_in_transition(self) -> None:
        spec = base_spec()
        spec["transitions"][0]["weight"] = 3
        self.assert_structural(spec)

    def test_structural_failure_skips_graph_rules(self) -> None:
        spec = base_spec()
        spec["states"][0]["id"] = "Start Here"
        spec["initial"] = "ghost"
        self.assertEqual({"S"}, codes(validate_spec(spec).errors))

    def test_optional_fields_are_accepted(self) -> None:
        spec = base_spec()
        spec["description"] = "An optional intro."
        spec["states"][0]["annotation"] = "An optional note."
        spec["transitions"][0]["description"] = "An optional hint."
        self.assertEqual([], validate_spec(spec).errors)


class LoadSpecTest(unittest.TestCase):
    """load_spec: reading, parsing and raising SpecError."""

    def test_loads_valid_fixture(self) -> None:
        data = load_spec(os.path.join(FIXTURES, "valid_minimal.json"))
        self.assertEqual("start", data["initial"])

    def test_invalid_fixture_raises_with_messages(self) -> None:
        with self.assertRaises(SpecError) as caught:
            load_spec(os.path.join(FIXTURES, "invalid_e1.json"))
        self.assertIn("E1", codes(caught.exception.messages))

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(SpecError) as caught:
            load_spec(os.path.join(FIXTURES, "no_such_file.json"))
        self.assertEqual(1, len(caught.exception.messages))

    def test_broken_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "broken.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            with self.assertRaises(SpecError) as caught:
                load_spec(path)
        self.assertIn("not valid JSON", caught.exception.messages[0])

    def test_fixture_validates_cleanly(self) -> None:
        with open(os.path.join(FIXTURES, "valid_minimal.json"), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        result = validate_spec(data)
        self.assertEqual([], result.errors)
        self.assertEqual([], result.warnings)


if __name__ == "__main__":
    unittest.main()
