"""Foundation for static PPTX inspection."""

from importlib.metadata import version

__version__ = version("pptviper")

from pptviper.config import Config
from pptviper.geometry import Bounds
from pptviper.inspection import inspect
from pptviper.report import Report

__all__ = ["Bounds", "Config", "Report", "inspect", "__version__"]
