import pytest

from mxalign.runner import Runner


def _runner(datasets: dict, alignment: dict) -> Runner:
    runner = Runner({"datasets": {}, "alignment": alignment})
    runner.datasets = datasets
    return runner


def test_align_runs_time_alignment_without_time_section(ds_fcst, ds_obs):
    runner = _runner(
        {"fcst": ds_fcst, "obs": ds_obs},
        {"reference": "obs", "broadcast_nans": False},
    )
    runner.align()
    # Global time alignment reshapes the observation reference onto the forecast grid
    assert runner.datasets["obs"].mx.is_forecast()


def test_align_time_rejects_unknown_options(ds_fcst, ds_obs):
    runner = _runner({"fcst": ds_fcst, "obs": ds_obs}, {"reference": "obs"})
    with pytest.raises(ValueError, match="Unknown option.*return_as"):
        runner.align_time({"return_as": "forecast"}, reference_name="obs")
