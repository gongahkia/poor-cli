import pytest

from poor_cli.exceptions import ValidationError
from poor_cli.parallel_agents import SubTask


def test_subtask_accepts_latent_communication_mode():
    task = SubTask(prompt="x", communication_mode="latent")
    assert task.communication_mode == "latent"


def test_subtask_rejects_unknown_communication_mode():
    with pytest.raises(ValidationError):
        SubTask(prompt="x", communication_mode="invalid")
