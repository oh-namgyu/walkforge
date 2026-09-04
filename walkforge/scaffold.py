"""The example spec written by ``walkforge init``.

The template is a small incident response flow: it branches on severity,
loops back to triage when a fix does not hold, and finishes in one of two
end states. It is expected to validate with zero errors and zero warnings.
"""

import copy
import json
from typing import Any, Dict

DEFAULT_FILENAME = "walkthrough.json"

_TEMPLATE: Dict[str, Any] = {
    "title": "Incident response walkthrough",
    "description": (
        "A short on-call drill: acknowledge the page, judge how bad it is, "
        "then either mitigate or watch and wait until the incident closes."
    ),
    "initial": "alert_received",
    "states": [
        {
            "id": "alert_received",
            "name": "Alert received",
            "description": "A monitor fired and paged the on-call engineer.",
            "annotation": "Acknowledge within five minutes so the page stops escalating.",
        },
        {
            "id": "triage",
            "name": "Triage severity",
            "description": (
                "Check the dashboard and the recent deploy log, then decide "
                "whether users are affected right now."
            ),
        },
        {
            "id": "mitigate",
            "name": "Mitigate",
            "description": "Roll back the suspect deploy or shift traffic away from the bad region.",
            "annotation": "Mitigation comes before diagnosis: stop the bleeding first.",
        },
        {
            "id": "monitor",
            "name": "Monitor",
            "description": "Nothing is on fire yet. Watch the error rate for fifteen minutes.",
        },
        {
            "id": "postmortem",
            "name": "Write the postmortem",
            "description": "The incident is over. Record the timeline, the cause and the follow-ups.",
            "is_end": True,
        },
        {
            "id": "resolved",
            "name": "Resolved without action",
            "description": "Metrics recovered on their own. Close the incident and note the false alarm.",
            "is_end": True,
        },
    ],
    "transitions": [
        {
            "from": "alert_received",
            "to": "triage",
            "label": "Acknowledge the page",
            "description": "Claim the incident so everyone knows who is driving.",
        },
        {"from": "triage", "to": "mitigate", "label": "Users are affected"},
        {"from": "triage", "to": "monitor", "label": "No user impact yet"},
        {
            "from": "mitigate",
            "to": "postmortem",
            "label": "Error rate is back to normal",
            "description": "The mitigation held for at least ten minutes.",
        },
        {"from": "mitigate", "to": "triage", "label": "Mitigation did not help"},
        {"from": "monitor", "to": "resolved", "label": "Metrics recovered on their own"},
        {"from": "monitor", "to": "triage", "label": "Symptoms came back"},
    ],
}


def example_spec() -> Dict[str, Any]:
    """Return a fresh copy of the template spec."""
    return copy.deepcopy(_TEMPLATE)


def target_path(name: str = DEFAULT_FILENAME) -> str:
    """Return the file name to create, appending ``.json`` when missing."""
    return name if name.endswith(".json") else name + ".json"


def write_scaffold(name: str = DEFAULT_FILENAME) -> str:
    """Write the template spec and return the path created.

    Raises ``FileExistsError`` when the target already exists; the file is
    never overwritten.
    """
    path = target_path(name)
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(example_spec(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path
