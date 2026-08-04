"""The one compiled Mission 97 workflow and its three compiled actions."""

from __future__ import annotations

from offchain.research.admission import canonical_hash

from .models import WorkflowDefinition, WorkflowStep


CAPTURE_STEP_ID = "CAPTURE_CONTROL_PLANE_SNAPSHOT"
VERIFY_STEP_ID = "VERIFY_CONTROL_PLANE_SNAPSHOT"
PUBLISH_STEP_ID = "PUBLISH_OBSERVATION_MANIFEST"

CAPTURE_ACTION_ID = "CAPTURE_RESEARCH_CONTROL_PLANE_SNAPSHOT_V1"
VERIFY_ACTION_ID = "VERIFY_RESEARCH_CONTROL_PLANE_SNAPSHOT_V1"
PUBLISH_ACTION_ID = "PUBLISH_RESEARCH_OBSERVATION_MANIFEST_V1"

_CORE = {
    "workflow_definition_id": "RESEARCH_OBSERVATION_REFRESH_V1",
    "workflow_definition_version": 1,
    "steps": [
        {"step_id": CAPTURE_STEP_ID, "action_id": CAPTURE_ACTION_ID},
        {"step_id": VERIFY_STEP_ID, "action_id": VERIFY_ACTION_ID},
        {"step_id": PUBLISH_STEP_ID, "action_id": PUBLISH_ACTION_ID},
    ],
    "retry_policy": {
        "maximum_attempts_per_step": 3,
        "retry_delays_seconds": [5, 30],
    },
}

WORKFLOW_DEFINITION_HASH = canonical_hash(_CORE)

RESEARCH_OBSERVATION_REFRESH_V1 = WorkflowDefinition(
    workflow_definition_id=_CORE["workflow_definition_id"],
    workflow_definition_version=1,
    steps=tuple(WorkflowStep(**item) for item in _CORE["steps"]),
    maximum_attempts_per_step=3,
    retry_delays_seconds=(5, 30),
    canonical_workflow_definition_hash=WORKFLOW_DEFINITION_HASH,
)

STEP_INDEX = {step.step_id: index for index, step in enumerate(RESEARCH_OBSERVATION_REFRESH_V1.steps)}
ACTION_BY_STEP = {step.step_id: step.action_id for step in RESEARCH_OBSERVATION_REFRESH_V1.steps}
