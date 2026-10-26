import importlib


def test_import_package():
    import mxalign  # noqa: F401


def test_public_api_exists():
    mxalign = importlib.import_module("mxalign")
    for name in mxalign.__all__:
        assert hasattr(mxalign, name), f"mxalign.__all__ lists missing name {name!r}"
