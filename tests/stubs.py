"""Stand-ins for the Anthropic client, shared by the model-facing tests.

Nothing here imports the anthropic package or opens a socket. Tests install
a stub by swapping ``llm._get_client`` inside the ``stubbed`` context
manager; every request the code makes is recorded for inspection.
"""

import contextlib
import json
from typing import Any, Dict, Iterator, List, Sequence

from walkforge import llm
from walkforge.scaffold import example_spec


class Block:
    """One text block of a stubbed response."""

    def __init__(self, text: str) -> None:
        self.text = text


class Reply:
    """A stubbed API response."""

    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.content = [Block(text)]
        self.stop_reason = stop_reason


class StubStream:
    """Context manager standing in for the SDK's streaming helper."""

    def __init__(self, reply: Reply) -> None:
        self.reply = reply
        self.closed = False

    def __enter__(self) -> "StubStream":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        self.closed = True
        return False

    def get_final_message(self) -> Reply:
        return self.reply


class StubMessages:
    """Records every request and hands back queued replies in order."""

    def __init__(self, replies: Sequence[Reply]) -> None:
        self.replies: List[Reply] = list(replies)
        self.calls: List[Dict[str, Any]] = []
        self.streams: List[StubStream] = []

    def stream(self, **kwargs: Any) -> StubStream:
        self.calls.append(kwargs)
        if not self.replies:
            raise AssertionError("the code under test made an unexpected extra request")
        opened = StubStream(self.replies.pop(0))
        self.streams.append(opened)
        return opened

    def create(self, **kwargs: Any) -> Reply:
        raise AssertionError("walkforge must stream: large max_tokens needs messages.stream()")


class StubClient:
    """Stand-in for anthropic.Anthropic()."""

    def __init__(self, replies: Sequence[Reply]) -> None:
        self.messages = StubMessages(replies)


@contextlib.contextmanager
def stubbed(*replies: Reply) -> Iterator[StubClient]:
    """Replace the client factory for the duration of the block."""
    client = StubClient(replies)
    original = llm._get_client
    llm._get_client = lambda: client
    try:
        yield client
    finally:
        llm._get_client = original


def as_reply(spec: Dict[str, Any], stop_reason: str = "end_turn") -> Reply:
    """Wrap a spec as the model would return it."""
    return Reply(json.dumps(spec), stop_reason)


def broken_spec() -> Dict[str, Any]:
    """A spec that is structurally fine but breaks graph rule E1."""
    spec = example_spec()
    spec["initial"] = "ghost"
    return spec
