import numpy as np
import pandas as pd
import xarray as xr

from mlwp_data_specs.api import TIME_TRAIT_ATTR
from mlwp_data_specs.specs.traits.time_coordinate import Time


def _add_valid_time(ds_fcst: xr.Dataset) -> xr.Dataset:
    """Add a 2-D ``valid_time`` coordinate (``reference_time + lead_time``) to a forecast dataset."""
    valid_time = (
        ds_fcst["reference_time"].values[:, np.newaxis] + ds_fcst["lead_time"].values
    )
    return ds_fcst.assign_coords(
        {"valid_time": (["reference_time", "lead_time"], valid_time)}
    )


def align_forecast_to_observation(
    ds_fcst: xr.Dataset,
    ds_obs: xr.Dataset,
    lead_time: str | list | np.timedelta64 = "shortest",
) -> xr.Dataset:
    """Stack ``ds_fcst`` to valid_time, deduplicate by ``lead_time`` strategy, and reindex to ``ds_obs.valid_time``."""
    ds_with_vt = _add_valid_time(ds_fcst)
    ds_stacked = ds_with_vt.stack(time=["reference_time", "lead_time"]).reset_index(
        "time"
    )

    vt_vals = ds_stacked.valid_time.values
    lt_vals = ds_stacked.lead_time.values

    if isinstance(lead_time, str) and lead_time in ("shortest", "longest"):
        df = pd.DataFrame({"vt": vt_vals, "lt": lt_vals})
        agg = "min" if lead_time == "shortest" else "max"
        is_candidate = (df.groupby("vt")["lt"].transform(agg) == df["lt"]).values
    else:
        requested = _parse_lead_times(lead_time)
        missing = np.setdiff1d(requested, lt_vals)
        if missing.size:
            raise ValueError(
                f"lead_time(s) {pd.to_timedelta(missing).tolist()} not in forecast "
                f"lead times {pd.to_timedelta(np.unique(lt_vals)).tolist()}"
            )
        is_candidate = np.isin(lt_vals, requested)

    # Among candidate entries keep the first per valid_time (handles ties: the
    # same valid_time reached via several reference_times)
    candidate_positions = np.where(is_candidate)[0]
    _, first_in_group = np.unique(vt_vals[candidate_positions], return_index=True)
    positions = candidate_positions[first_in_group]

    ds_1d = ds_stacked.isel(time=positions)
    ds_1d = ds_1d.swap_dims({"time": "valid_time"})
    ds_1d = ds_1d.drop_vars(
        [v for v in ["reference_time", "lead_time", "time"] if v in ds_1d.coords]
    )
    ds_1d = ds_1d.transpose("valid_time", ...)

    ds_1d = ds_1d.reindex(valid_time=ds_obs.valid_time)
    ds_1d.attrs[TIME_TRAIT_ATTR] = Time.OBSERVATION.value
    return ds_1d


def _parse_lead_times(lead_time) -> np.ndarray:
    """Convert one or more lead times (timedelta-like or strings such as ``"6h"``) to ``timedelta64[ns]``."""
    values = np.atleast_1d(np.asarray(lead_time, dtype=object))
    # np.timedelta64 subclasses np.number, so exclude it explicitly
    if any(
        isinstance(v, (int, float, np.number)) and not isinstance(v, np.timedelta64)
        for v in values
    ):
        raise ValueError(
            f"lead_time {lead_time!r} needs a unit, e.g. '6h' or np.timedelta64(6, 'h')."
        )
    try:
        return pd.to_timedelta(values).to_numpy().astype("timedelta64[ns]")
    except ValueError:
        raise ValueError(
            f"Unknown lead_time option for F→O alignment: {lead_time!r}. Use "
            "'shortest', 'longest', or one or more lead times such as '6h'."
        ) from None


def align_observation_to_forecast(
    ds_obs: xr.Dataset, ds_fcst: xr.Dataset
) -> xr.Dataset:
    """Broadcast 1-D observations onto ``(reference_time, lead_time)`` by selecting via forecast valid times."""
    ds_fcst_with_vt = _add_valid_time(ds_fcst)
    valid_time_2d = ds_fcst_with_vt["valid_time"]  # shape (reference_time, lead_time)

    # Reindex obs onto all unique fcst valid_times (NaN-fills fcst valid_times not in obs)
    fcst_vt_flat = np.unique(valid_time_2d.values.ravel())
    obs_reindexed = ds_obs.reindex(valid_time=fcst_vt_flat)

    # sel with a 2D DataArray indexer broadcasts 1D obs → (reference_time, lead_time)
    ds_out = obs_reindexed.sel(valid_time=valid_time_2d)

    ds_out.attrs[TIME_TRAIT_ATTR] = Time.FORECAST.value
    return ds_out


def align_observation_to_observation(ds1: xr.Dataset, ds2: xr.Dataset) -> xr.Dataset:
    """Reindex ``ds1`` to ``ds2.valid_time`` with NaN-fill for missing times."""
    return ds1.reindex(valid_time=ds2.valid_time)


def align_forecast_to_forecast(
    ds1: xr.Dataset, ds2: xr.Dataset, lead_time: str = "reference"
) -> xr.Dataset:
    """Reindex ``ds1`` to ``ds2.reference_time`` and align lead times per ``lead_time`` strategy."""
    ds_out = ds1.reindex(reference_time=ds2.reference_time)

    if lead_time == "reference":
        ds_out = ds_out.reindex(lead_time=ds2.lead_time)
    elif lead_time == "intersection":
        common_lt = np.intersect1d(ds_out.lead_time.values, ds2.lead_time.values)
        ds_out = ds_out.sel(lead_time=common_lt)
    elif lead_time == "union":
        all_lt = np.union1d(ds_out.lead_time.values, ds2.lead_time.values)
        ds_out = ds_out.reindex(lead_time=all_lt)
    else:
        raise ValueError(f"Unknown lead_time option for F→F alignment: {lead_time!r}")

    # Refresh valid_time
    if "valid_time" in ds_out.coords:
        ds_out = ds_out.drop_vars("valid_time")
    return _add_valid_time(ds_out)
