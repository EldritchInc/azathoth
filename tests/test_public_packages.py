"""Tests for the public package surface."""

import importlib
import pkgutil

import azathoth


def subpackage_names() -> tuple[str, ...]:
    """Return every importable package below the root package, sorted."""

    return tuple(
        sorted(
            module.name
            for module in pkgutil.walk_packages(
                azathoth.__path__,
                prefix="azathoth.",
            )
            if module.ispkg
        )
    )


def test_subpackages_are_discovered() -> None:
    names = subpackage_names()

    assert "azathoth.cli" in names
    assert "azathoth.cli.rendering" in names
    assert "azathoth.workflows" in names


def test_every_subpackage_declares_a_public_api() -> None:
    without_public_api = tuple(
        name
        for name in subpackage_names()
        if not getattr(
            importlib.import_module(name),
            "__all__",
            (),
        )
    )

    assert without_public_api == ()
