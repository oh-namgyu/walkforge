"""Loading and validation of walkforge walkthrough specs.

Validation has two layers.

Layer A -- structural rules, declared in ``spec_schema.json`` and enforced
by the small schema-driven checker below (types, required properties,
string patterns and lengths, array bounds, ``additionalProperties: false``).
Structural messages are prefixed ``S:`` and carry the offending JSON path.

Layer B -- graph rules, implemented in this module:

====  ========  ====================================================
Code  Severity  Rule
====  ========  ====================================================
E1    error     ``initial`` must name an existing state
E2    error     transition ``from``/``to`` must name existing states
E3    error     state ids must be unique
E4    error     ``(from, label)`` pairs must be unique
E5    error     a transition must not be a self-loop
E6    error     a non-end state must have an outgoing transition
E7    error     an end state must be reachable from ``initial``
E8    error     every reachable non-end state must reach an end state
W1    warning   state unreachable from ``initial``
====  ========  ====================================================

End states may have outgoing transitions: re-exploration loops are allowed.
Layer B only runs when layer A found no problem, so graph rules can assume
well-formed input.
"""

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec_schema.json")

_schema_cache: Optional[Dict[str, Any]] = None


class SpecError(Exception):
    """Raised when a spec cannot be read or fails validation."""

    def __init__(self, messages: Sequence[str]) -> None:
        self.messages: List[str] = list(messages)
        super().__init__("; ".join(self.messages))


class ValidationResult:
    """Outcome of validating a spec document."""

    def __init__(self, errors: Sequence[str], warnings: Sequence[str]) -> None:
        self.errors: List[str] = list(errors)
        self.warnings: List[str] = list(warnings)

    @property
    def ok(self) -> bool:
        """True when no error was found (warnings are tolerated)."""
        return not self.errors

    def __repr__(self) -> str:
        return "ValidationResult(errors=%r, warnings=%r)" % (self.errors, self.warnings)


def load_schema() -> Dict[str, Any]:
    """Return the parsed structural JSON Schema, cached after first read."""
    global _schema_cache
    if _schema_cache is None:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
            _schema_cache = json.load(handle)
    return _schema_cache


# --------------------------------------------------------------------------
# Layer A: schema-driven structural checker
# --------------------------------------------------------------------------

_TYPES: Dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
}


def _type_matches(value: Any, type_name: str) -> bool:
    """Return True when ``value`` matches the JSON Schema type name."""
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name in ("integer", "number"):
        return isinstance(value, _TYPES[type_name]) and not isinstance(value, bool)
    expected = _TYPES.get(type_name)
    return expected is not None and isinstance(value, expected)


def _fail(path: str, message: str) -> str:
    """Format one structural failure message."""
    return "S: %s: %s" % (path or "<root>", message)


def _check_object(value: Dict[str, Any], schema: Dict[str, Any], path: str) -> List[str]:
    """Check required properties, unknown properties and nested properties."""
    messages: List[str] = []
    properties: Dict[str, Any] = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in value:
            messages.append(_fail(path, "missing required property '%s'" % name))
    if schema.get("additionalProperties") is False:
        for name in sorted(value):
            if name not in properties:
                messages.append(_fail(path, "unknown property '%s'" % name))
    for name, subschema in properties.items():
        if name in value:
            child = "%s.%s" % (path, name) if path else name
            messages.extend(check_structure(value[name], subschema, child))
    return messages


def _check_array(value: List[Any], schema: Dict[str, Any], path: str) -> List[str]:
    """Check array bounds and every item against the item schema."""
    messages: List[str] = []
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if minimum is not None and len(value) < minimum:
        messages.append(_fail(path, "expected at least %d item(s), got %d" % (minimum, len(value))))
    if maximum is not None and len(value) > maximum:
        messages.append(_fail(path, "expected at most %d item(s), got %d" % (maximum, len(value))))
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            messages.extend(check_structure(item, item_schema, "%s[%d]" % (path, index)))
    return messages


def _check_string(value: str, schema: Dict[str, Any], path: str) -> List[str]:
    """Check length bounds and the optional regular expression pattern."""
    messages: List[str] = []
    minimum = schema.get("minLength")
    maximum = schema.get("maxLength")
    if minimum is not None and len(value) < minimum:
        messages.append(_fail(path, "shorter than %d character(s)" % minimum))
    if maximum is not None and len(value) > maximum:
        messages.append(_fail(path, "longer than %d character(s)" % maximum))
    pattern = schema.get("pattern")
    if pattern is not None and re.search(pattern, value) is None:
        messages.append(_fail(path, "does not match pattern %s" % pattern))
    return messages


def check_structure(value: Any, schema: Dict[str, Any], path: str = "") -> List[str]:
    """Validate ``value`` against a flat, non-recursive JSON Schema subset.

    Supported keywords: type, required, properties, additionalProperties,
    items, minItems, maxItems, minLength, maxLength, pattern. Anything else
    (title, description, default, $schema) is documentation and ignored.
    """
    type_name = schema.get("type")
    if type_name is not None and not _type_matches(value, type_name):
        return [_fail(path, "expected %s, got %s" % (type_name, type(value).__name__))]
    if type_name == "object":
        return _check_object(value, schema, path)
    if type_name == "array":
        return _check_array(value, schema, path)
    if type_name == "string":
        return _check_string(value, schema, path)
    return []


# --------------------------------------------------------------------------
# Layer B: graph rules
# --------------------------------------------------------------------------


def _reachable(start: str, edges: Dict[str, List[str]]) -> Set[str]:
    """Return the set of nodes reachable from ``start`` (breadth first)."""
    seen: Set[str] = {start}
    queue: List[str] = [start]
    while queue:
        current = queue.pop(0)
        for target in edges.get(current, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _check_states(states: Sequence[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Apply E3 and return (messages, ordered unique state ids)."""
    messages: List[str] = []
    ids: List[str] = []
    for state in states:
        state_id = state["id"]
        if state_id in ids:
            messages.append("E3: duplicate state id '%s'" % state_id)
        else:
            ids.append(state_id)
    return messages, ids


def _check_transitions(
    transitions: Sequence[Dict[str, Any]], known: Iterable[str]
) -> Tuple[List[str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Apply E2, E4, E5 and return (messages, outgoing map, reverse map)."""
    messages: List[str] = []
    known_ids = set(known)
    outgoing: Dict[str, List[str]] = {}
    incoming: Dict[str, List[str]] = {}
    seen_labels: Set[Tuple[str, str]] = set()
    for transition in transitions:
        source, target, label = transition["from"], transition["to"], transition["label"]
        unknown = [name for name in (source, target) if name not in known_ids]
        for name in unknown:
            messages.append(
                "E2: transition '%s' -> '%s' references unknown state '%s'" % (source, target, name)
            )
        if source == target:
            messages.append("E5: transition '%s' -> '%s' is a self-loop" % (source, target))
        key = (source, label)
        if key in seen_labels:
            messages.append("E4: duplicate label '%s' on transitions from '%s'" % (label, source))
        seen_labels.add(key)
        if not unknown and source != target:
            outgoing.setdefault(source, []).append(target)
            incoming.setdefault(target, []).append(source)
    return messages, outgoing, incoming


def _check_flow(
    states: Sequence[Dict[str, Any]],
    initial: str,
    outgoing: Dict[str, List[str]],
    incoming: Dict[str, List[str]],
    ids: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """Apply E1, E6, E7, E8 and W1. Returns (errors, warnings)."""
    errors: List[str] = []
    warnings: List[str] = []
    end_ids = [state["id"] for state in states if state.get("is_end", False)]
    for state in states:
        state_id = state["id"]
        if not state.get("is_end", False) and not outgoing.get(state_id):
            errors.append("E6: state '%s' is a dead end: not an end state and has no transitions" % state_id)
    if initial not in set(ids):
        errors.append("E1: initial state '%s' is not a declared state" % initial)
        return errors, warnings
    reachable = _reachable(initial, outgoing)
    if not [state_id for state_id in end_ids if state_id in reachable]:
        errors.append("E7: no end state is reachable from initial state '%s'" % initial)
    can_finish: Set[str] = set()
    for end_id in end_ids:
        can_finish |= _reachable(end_id, incoming)
    for state in states:
        state_id = state["id"]
        if state_id not in reachable:
            warnings.append("W1: state '%s' is unreachable from initial state '%s'" % (state_id, initial))
        elif not state.get("is_end", False) and state_id not in can_finish:
            errors.append("E8: state '%s' is reachable but cannot reach any end state" % state_id)
    return errors, warnings


def validate_spec(data: Any) -> ValidationResult:
    """Validate a spec document and return every error and warning found."""
    structural = check_structure(data, load_schema())
    if structural:
        return ValidationResult(structural, [])
    states: List[Dict[str, Any]] = data["states"]
    state_messages, ids = _check_states(states)
    transition_messages, outgoing, incoming = _check_transitions(data["transitions"], ids)
    flow_errors, warnings = _check_flow(states, data["initial"], outgoing, incoming, ids)
    return ValidationResult(state_messages + transition_messages + flow_errors, warnings)


def load_spec(path: str) -> Dict[str, Any]:
    """Read, parse and validate the spec at ``path``.

    Raises ``SpecError`` carrying every message when the file cannot be read,
    is not valid JSON, or fails validation. Warnings never block loading; call
    ``validate_spec`` on the returned document to collect them.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise SpecError(["cannot read spec '%s': %s" % (path, exc.strerror or exc)])
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise SpecError(["spec '%s' is not valid JSON: %s" % (path, exc)])
    result = validate_spec(data)
    if result.errors:
        raise SpecError(result.errors)
    return data
