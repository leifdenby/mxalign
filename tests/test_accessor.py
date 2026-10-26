"""Tests for ``ds.mx`` accessor state: trait reading and non-mutation."""

import cartopy.crs as ccrs
import numpy as np
import pytest
import xarray as xr

import mxalign  # registers ds.mx accessor  # noqa: F401


@pytest.fixture
def ds_grid() -> xr.Dataset:
    """2×2 grid stacked to grid_index, lon/lat in 0..1."""
    return xr.Dataset(
        {"temp": ("grid_index", np.arange(4.0))},
        coords={
            "longitude": ("grid_index", [0.0, 1.0, 0.0, 1.0]),
            "latitude": ("grid_index", [0.0, 0.0, 1.0, 1.0]),
        },
        attrs={"mlwp_space_trait": "grid", "mlwp_time_trait": "forecast"},
    )


class TestTraits:
    def test_predicates_follow_attr_changes(self, ds_grid):
        assert ds_grid.mx.is_forecast()
        ds_grid.attrs["mlwp_time_trait"] = "observation"
        assert ds_grid.mx.is_observation()
        assert not ds_grid.mx.is_forecast()

    def test_missing_trait_raises_on_use_not_on_access(self):
        ds = xr.Dataset({"temp": ("grid_index", np.arange(4.0))})
        assert ds.mx.is_stacked()  # needs no traits
        with pytest.raises(KeyError, match="mlwp_space_trait"):
            ds.mx.is_grid()


class TestNoMutation:
    def test_add_xy_with_crs_leaves_dataset_untouched(self, ds_grid):
        out = ds_grid.mx.add_xy(crs=ccrs.PlateCarree())

        np.testing.assert_allclose(out["xc"].values, ds_grid["longitude"].values)
        assert "crs" not in ds_grid.attrs
        # The accessor still sees the original dataset, which has no CRS
        with pytest.raises(ValueError, match="No CRS"):
            ds_grid.mx.add_xy()

    def test_unstack_with_crs_leaves_dataset_untouched(self, ds_grid):
        out = ds_grid.mx.unstack(
            crs=ccrs.PlateCarree(), nx=2, ny=2, lon_ll=0, lat_ll=0, dx=1, dy=1
        )

        assert out["temp"].dims == ("yc", "xc")
        assert "crs" not in ds_grid.attrs
        assert ds_grid.mx.stack() is ds_grid


class TestStack:
    def test_stack_regular_latlon_grid(self):
        ds = xr.Dataset(
            {"temp": (["latitude", "longitude"], np.zeros((2, 3)))},
            coords={"latitude": [0.0, 1.0], "longitude": [0.0, 1.0, 2.0]},
            attrs={"mlwp_space_trait": "grid", "mlwp_time_trait": "forecast"},
        )

        out = ds.mx.stack()

        assert out["temp"].dims == ("grid_index",)
        assert out.sizes["grid_index"] == 6
        assert out["latitude"].dims == out["longitude"].dims == ("grid_index",)
