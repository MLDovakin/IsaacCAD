"""kcad — parametric, checkable assembly toolkit for USD / Isaac Sim.

Core idea: the scene is not edited, it is rebuilt from a spec, and design intent is
stored as machine-checkable invariants rather than in a chat transcript.
"""
from .build import build, rebuild
from .checks import run_all
from .spec import load

__version__ = "0.1.0"
__all__ = ["load", "build", "rebuild", "run_all", "__version__"]
