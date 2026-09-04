"""Tests for the model layer: schema transform, client setup, conversation.

No test here imports the anthropic package or opens a socket: every test
either replaces ``llm._get_client`` with a stub or checks the failure path
that runs before a client is ever built.
"""

import importlib.util
import os
import subprocess
import sys
import unittest
from typing import Any, Dict, List
from unittest import mock

from stubs import Reply, as_reply, broken_spec, stubbed

from walkforge import llm
from walkforge.scaffold import example_spec

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = "placeholder-for-tests"


def walk(node: Any, seen: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect every schema node below ``node``, including itself."""
    if isinstance(node, dict):
        seen.append(node)
        for value in node.get("properties", {}).values():
            walk(value, seen)
        if isinstance(node.get("items"), dict):
            walk(node["items"], seen)
    return seen


class SchemaTransformTest(unittest.TestCase):
    """structured_schema() must satisfy the structured-outputs subset."""

    def setUp(self) -> None:
        self.schema = llm.structured_schema()
        self.nodes = walk(self.schema, [])

    def test_custom_and_meta_keys_are_dropped(self) -> None:
        self.assertNotIn("version", self.schema)
        self.assertNotIn("$schema", self.schema)
        self.assertEqual(1, llm.load_schema()["version"])

    def test_every_object_forbids_extra_properties(self) -> None:
        objects = [node for node in self.nodes if node.get("type") == "object"]
        self.assertEqual(3, len(objects))
        for node in objects:
            self.assertIs(False, node["additionalProperties"])

    def test_every_property_is_required(self) -> None:
        for node in self.nodes:
            if node.get("type") == "object":
                self.assertEqual(list(node["properties"].keys()), node["required"])

    def test_unsupported_keywords_are_removed(self) -> None:
        for node in self.nodes:
            for keyword in ("minLength", "maxLength", "pattern", "minItems", "maxItems", "default"):
                self.assertNotIn(keyword, node, node.get("description", ""))

    def test_shape_still_matches_the_spec_document(self) -> None:
        self.assertEqual("object", self.schema["type"])
        self.assertEqual(
            ["title", "description", "initial", "states", "transitions"],
            list(self.schema["properties"].keys()),
        )
        state = self.schema["properties"]["states"]["items"]
        self.assertEqual(["id", "name", "description", "annotation", "is_end"], state["required"])
        self.assertEqual("boolean", state["properties"]["is_end"]["type"])

    def test_on_disk_schema_is_left_alone(self) -> None:
        llm.structured_schema()
        self.assertIn("minLength", llm.load_schema()["properties"]["title"])


class ClientSetupTest(unittest.TestCase):
    """The optional dependency and the API key are checked before any call."""

    def test_default_model(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("claude-opus-5", llm.default_model())
        with mock.patch.dict(os.environ, {llm.MODEL_ENV: "claude-sonnet-5"}):
            self.assertEqual("claude-sonnet-5", llm.default_model())

    def test_missing_key_is_reported(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(llm.LLMNotConfigured) as caught:
                llm._get_client()
        self.assertIn(llm.KEY_ENV, str(caught.exception))

    @unittest.skipIf(
        importlib.util.find_spec("anthropic") is not None, "the anthropic package is installed"
    )
    def test_missing_package_is_reported(self) -> None:
        with mock.patch.dict(os.environ, {llm.KEY_ENV: PLACEHOLDER}):
            with self.assertRaises(llm.LLMNotConfigured) as caught:
                llm._get_client()
        self.assertIn("anthropic", str(caught.exception))


class ConversationTest(unittest.TestCase):
    """Request shape, retry behaviour and response handling."""

    def test_generate_returns_the_parsed_spec(self) -> None:
        with stubbed(as_reply(example_spec())) as client:
            spec = llm.generate_spec("An outage", "claude-opus-5")
        self.assertEqual(example_spec(), spec)
        self.assertEqual(1, len(client.messages.calls))

    def test_request_carries_the_structured_output_config(self) -> None:
        with stubbed(as_reply(example_spec())) as client:
            llm.generate_spec("An outage", "claude-opus-5")
        call = client.messages.calls[0]
        self.assertEqual("claude-opus-5", call["model"])
        self.assertEqual(llm.MAX_TOKENS, call["max_tokens"])
        self.assertEqual(llm.SYSTEM_PROMPT, call["system"])
        self.assertEqual("user", call["messages"][0]["role"])
        self.assertIn("An outage", call["messages"][0]["content"])
        fmt = call["output_config"]["format"]
        self.assertEqual("json_schema", fmt["type"])
        self.assertEqual(llm.structured_schema(), fmt["schema"])

    def test_requests_are_streamed_and_the_stream_is_closed(self) -> None:
        with stubbed(as_reply(example_spec())) as client:
            llm.generate_spec("An outage", "claude-opus-5")
        self.assertEqual(1, len(client.messages.streams))
        self.assertTrue(client.messages.streams[0].closed)

    def test_each_attempt_opens_its_own_stream(self) -> None:
        replies = (as_reply(example_spec(), "max_tokens"), as_reply(example_spec()))
        with stubbed(*replies) as client:
            llm.generate_spec("An outage", "claude-opus-5")
        self.assertEqual(2, len(client.messages.streams))
        self.assertTrue(all(opened.closed for opened in client.messages.streams))

    def test_max_tokens_triggers_one_larger_retry(self) -> None:
        replies = (as_reply(example_spec(), "max_tokens"), as_reply(example_spec()))
        with stubbed(*replies) as client:
            spec = llm.generate_spec("An outage", "claude-opus-5")
        self.assertEqual(example_spec(), spec)
        limits = [call["max_tokens"] for call in client.messages.calls]
        self.assertEqual([llm.MAX_TOKENS, llm.RETRY_MAX_TOKENS], limits)

    def test_second_max_tokens_is_an_error(self) -> None:
        replies = (as_reply(example_spec(), "max_tokens"), as_reply(example_spec(), "max_tokens"))
        with stubbed(*replies):
            with self.assertRaises(llm.LLMError) as caught:
                llm.generate_spec("An outage", "claude-opus-5")
        self.assertIn("ran out of room", str(caught.exception))

    def test_refusal_is_an_error(self) -> None:
        with stubbed(as_reply(example_spec(), "refusal")):
            with self.assertRaises(llm.LLMError) as caught:
                llm.generate_spec("An outage", "claude-opus-5")
        self.assertIn("declined", str(caught.exception))

    def test_unparsable_reply_is_an_error(self) -> None:
        with stubbed(Reply("here is your walkthrough!")):
            with self.assertRaises(llm.LLMError) as caught:
                llm.generate_spec("An outage", "claude-opus-5")
        self.assertIn("valid JSON", str(caught.exception))

    def test_non_object_reply_is_an_error(self) -> None:
        with stubbed(Reply("[1, 2, 3]")):
            with self.assertRaises(llm.LLMError) as caught:
                llm.generate_spec("An outage", "claude-opus-5")
        self.assertIn("not a walkthrough", str(caught.exception))

    def test_empty_reply_is_an_error(self) -> None:
        empty = Reply("")
        empty.content = []
        with stubbed(empty):
            with self.assertRaises(llm.LLMError):
                llm.generate_spec("An outage", "claude-opus-5")

    def test_revise_sends_the_current_spec_and_instruction(self) -> None:
        with stubbed(as_reply(example_spec())) as client:
            llm.revise_spec(example_spec(), "Add a rollback branch", "claude-opus-5")
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertIn("Add a rollback branch", prompt)
        self.assertIn("alert_received", prompt)

    def test_repair_quotes_every_rule_message(self) -> None:
        with stubbed(as_reply(example_spec())) as client:
            llm.repair_spec(broken_spec(), ["E1: initial state 'ghost' ..."], "claude-opus-5")
        prompt = client.messages.calls[0]["messages"][0]["content"]
        self.assertIn("E1: initial state 'ghost' ...", prompt)

    def test_transcript_records_both_sides(self) -> None:
        transcript: List[str] = []
        with stubbed(as_reply(example_spec())):
            llm.generate_spec("An outage", "claude-opus-5", transcript=transcript)
        self.assertEqual(2, len(transcript))
        self.assertIn("An outage", transcript[0])
        self.assertIn("alert_received", transcript[1])

    def test_transcript_is_optional(self) -> None:
        with stubbed(as_reply(example_spec())):
            self.assertEqual(example_spec(), llm.generate_spec("An outage", "claude-opus-5"))


class RenderPathPurityTest(unittest.TestCase):
    """The offline commands must not pull in the optional dependency."""

    def run_probe(self, source: str) -> str:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = REPO_ROOT + os.pathsep + environment.get("PYTHONPATH", "")
        process = subprocess.run(
            [sys.executable, "-c", source],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(0, process.returncode, process.stderr)
        return process.stdout.strip()

    def test_render_path_imports_neither_anthropic_nor_llm(self) -> None:
        probe = (
            "import walkforge.renderer, walkforge.spec, walkforge.layout, walkforge.scaffold, sys;"
            "print('anthropic' in sys.modules, 'walkforge.llm' in sys.modules)"
        )
        self.assertEqual("False False", self.run_probe(probe))

    def test_importing_llm_does_not_import_anthropic(self) -> None:
        probe = "import walkforge.llm, sys; print('anthropic' in sys.modules)"
        self.assertEqual("False", self.run_probe(probe))


if __name__ == "__main__":
    unittest.main()
