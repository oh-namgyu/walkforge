"""Spec generation and revision through the Anthropic API.

The ``anthropic`` package is an optional dependency. It is imported lazily
inside ``_get_client`` so that ``init``, ``validate`` and ``render`` keep
working with nothing installed beyond the standard library.

The model is asked for a spec through structured outputs, using a schema
derived from ``spec_schema.json`` so there is only ever one source of truth
for the document shape. Whatever comes back is still checked by walkforge's
own validator: the schema pins the shape, the validator pins the rules.
"""

import json
import os
from typing import Any, Dict, List, Optional, Sequence

from .spec import load_schema

DEFAULT_MODEL = "claude-opus-5"
MODEL_ENV = "WALKFORGE_MODEL"
KEY_ENV = "ANTHROPIC_API_KEY"
MAX_TOKENS = 16000
RETRY_MAX_TOKENS = 32000

# Structured outputs accept a subset of JSON Schema: types, object shape,
# enums and annotations, but not length bounds, numeric bounds or patterns.
# Those keywords stay in spec_schema.json for walkforge's own checker and
# are removed from the copy sent to the model.
_UNSUPPORTED = ("minLength", "maxLength", "pattern", "minItems", "maxItems", "default")
_ROOT_ONLY = ("version", "$schema")

SYSTEM_PROMPT = """You design interactive walkthroughs: small state machines a
reader clicks through, one step at a time.

What makes a good walkthrough:
- Four to twelve states for a typical situation. Fewer feels thin, more is a
  manual rather than a walkthrough.
- Every state description says where the reader is and what is happening,
  in plain language, two or three sentences.
- Transition labels are the reader's own choices: short, imperative, concrete
  ("Roll back the deploy", not "Option A" or "The user rolls back").
- At least one real branch where the path genuinely forks, and at least one
  end state. Prefer honest decision points over a straight line of steps.
- Use the optional annotation for a caveat, a warning or a tip that would
  clutter the description.
- Loops back to an earlier state are welcome when a step can fail or repeat.

Hard rules the walkthrough must satisfy:
- Every id in initial, from and to must be a state you declared.
- State ids are unique, lowercase, and use only letters, digits, - and _.
- No transition may point at its own state.
- Every state that is not an end state needs at least one outgoing transition.
- Every state must be able to reach an end state by some path.
- Two transitions out of the same state must not share a label.
- Every state must be reachable from the initial state.

Write in English unless the situation is written in another language, in which
case write the whole walkthrough in that language."""


class LLMNotConfigured(Exception):
    """Raised when the optional model dependencies are not available."""


class LLMError(Exception):
    """Raised when the model runs but does not return a usable spec."""


def default_model() -> str:
    """Return the model id to use, honouring the environment override."""
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def _get_client() -> Any:
    """Build an API client, explaining precisely what is missing if it fails."""
    if not os.environ.get(KEY_ENV):
        raise LLMNotConfigured(
            "no API key found: set the %s environment variable to use this command" % KEY_ENV
        )
    try:
        import anthropic
    except ImportError:
        raise LLMNotConfigured(
            "the anthropic package is required for this command: pip install anthropic"
        )
    return anthropic.Anthropic()


# --------------------------------------------------------------------------
# Schema transform
# --------------------------------------------------------------------------


def _tighten(node: Any) -> Any:
    """Recursively apply the structured-outputs rules to one schema node."""
    if not isinstance(node, dict):
        return node
    clean: Dict[str, Any] = dict(
        (key, value) for key, value in node.items() if key not in _UNSUPPORTED
    )
    if clean.get("type") == "object" and "properties" in clean:
        clean["additionalProperties"] = False
        clean["properties"] = dict(
            (name, _tighten(value)) for name, value in clean["properties"].items()
        )
        clean["required"] = list(clean["properties"].keys())
    elif clean.get("type") == "array" and isinstance(clean.get("items"), dict):
        clean["items"] = _tighten(clean["items"])
    return clean


def structured_schema() -> Dict[str, Any]:
    """Return ``spec_schema.json`` adapted to the structured-outputs subset.

    Three changes: the custom ``version`` marker and ``$schema`` are dropped,
    every object forbids extra properties and lists all of its properties as
    required, and unsupported constraint keywords are removed. Making the
    optional fields required is safe here because none of them carry a minimum
    length: the model can answer with an empty string or ``false``.
    """
    schema = _tighten(load_schema())
    for key in _ROOT_ONLY:
        schema.pop(key, None)
    return schema


# --------------------------------------------------------------------------
# Conversation
# --------------------------------------------------------------------------


def _first_text(response: Any) -> str:
    """Return the first text block of a response."""
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    raise LLMError("the model returned no text to read")


def _create(client: Any, prompt: str, model: str, limit: int) -> Any:
    """Make one structured-output request and wait for the whole message.

    The request is streamed: the SDK refuses a non-streaming call with a
    ``max_tokens`` this large, because an idle connection would time out
    before a long answer arrives.
    """
    with client.messages.stream(
        model=model,
        max_tokens=limit,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": structured_schema()}},
    ) as stream:
        return stream.get_final_message()


def _converse(prompt: str, model: str, transcript: Optional[List[str]]) -> Dict[str, Any]:
    """Ask the model for a spec, retrying once if it ran out of room."""
    client = _get_client()
    if transcript is not None:
        transcript.append("--- request ---\n" + prompt)
    response = _create(client, prompt, model, MAX_TOKENS)
    if getattr(response, "stop_reason", None) == "max_tokens":
        response = _create(client, prompt, model, RETRY_MAX_TOKENS)
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise LLMError("the model declined to answer this request")
    if stop == "max_tokens":
        raise LLMError("the model ran out of room even after retrying with a larger limit")
    text = _first_text(response)
    if transcript is not None:
        transcript.append("--- response (stop_reason=%s) ---\n%s" % (stop, text))
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LLMError("the model did not return valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise LLMError("the model returned %s, not a walkthrough" % type(data).__name__)
    return data


def _as_json(spec: Dict[str, Any]) -> str:
    """Render a spec for inclusion in a prompt."""
    return json.dumps(spec, indent=2, ensure_ascii=False)


def generate_spec(
    situation: str, model: str, transcript: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Write a new walkthrough spec for a described situation.

    When ``transcript`` is given, the prompt and the raw reply are appended to
    it so the caller can save them for debugging.
    """
    prompt = "Design a walkthrough for this situation.\n\nSituation:\n" + situation
    return _converse(prompt, model, transcript)


def revise_spec(
    spec: Dict[str, Any], instruction: str, model: str, transcript: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Rewrite an existing spec according to an instruction."""
    prompt = (
        "Revise this walkthrough and return the complete revised version.\n\nInstruction:\n"
        + instruction
        + "\n\nCurrent walkthrough:\n"
        + _as_json(spec)
    )
    return _converse(prompt, model, transcript)


def repair_spec(
    spec: Dict[str, Any],
    errors: Sequence[str],
    model: str,
    transcript: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ask for a corrected spec, quoting the rules that were broken."""
    prompt = (
        "This walkthrough breaks walkforge rules. Fix every problem listed and "
        "return the complete corrected walkthrough.\n\nProblems:\n"
        + "\n".join("- " + message for message in errors)
        + "\n\nWalkthrough:\n"
        + _as_json(spec)
    )
    return _converse(prompt, model, transcript)
