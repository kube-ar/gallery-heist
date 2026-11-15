"""The reference solutions pass their checks; the starter files are 'not started'."""

import importlib
import importlib.util
import os

import pytest

from heist.case import ROOT
from heist.milestones import MILESTONES


def load(path):
    spec = importlib.util.spec_from_file_location(f"ref_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_reference_passes(mid):
    m = MILESTONES[mid]
    results = importlib.import_module(m.checks).run(load(ROOT / m.reference))
    failed = [(r.name, r.details[:2]) for r in results if not r.passed]
    assert failed == []


UPSTREAM = os.environ.get("GITHUB_REPOSITORY", "") == "kube-ar/gallery-heist" or os.environ.get("HEIST_UPSTREAM")


@pytest.mark.skipif(not UPSTREAM, reason="your copy has your code in the starter files, not the stubs")
@pytest.mark.parametrize("mid", sorted(MILESTONES))
def test_starter_is_not_started(mid):
    m = MILESTONES[mid]
    starter = load(ROOT / m.file)
    results = importlib.import_module(m.checks).run(starter)
    assert all(not r.started for r in results)
