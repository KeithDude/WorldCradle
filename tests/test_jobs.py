"""Background tasks: one at a time, with a status the page can follow."""
import pytest

import jobs
from games.base import ActionError


def test_a_job_runs_one_at_a_time_and_reports_how_it_ended():
    job = jobs.Job("test")
    assert job.status() == {"state": "idle"} and not job.running
    job.begin("busy!", label="Valheim", step="starting")
    assert job.running and job.get("label") == "Valheim"
    with pytest.raises(ActionError, match="busy!"):
        job.begin("busy!")
    job.step("copying", log=False)
    job.finish(False, "it broke", percent=40)
    s = job.status()
    assert s["state"] == "failed" and s["ok"] is False and s["message"] == "it broke"
    assert s["step"] == "copying" and s["percent"] == 40 and "finished_ts" in s
    job.begin("busy!", label="Palworld")             # a new run starts fresh
    assert "message" not in job.status() and job.get("label") == "Palworld"
