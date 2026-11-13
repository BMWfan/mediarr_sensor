"""Run backend regressions only after confirming the actual HA test target."""
from importlib.metadata import version
import unittest
from pathlib import Path
import sys

# Direct script execution puts scripts/, rather than the checkout, on sys.path.
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from homeassistant.const import __version__

if __version__ != '2026.11.1':
    raise SystemExit(f'Wrong HA test target: {__version__}; expected 2026.11.1')
frontend = version('home-assistant-frontend')
print(f'Verified Home Assistant {__version__}; frontend {frontend}', flush=True)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root / 'tests')))
raise SystemExit(0 if result.wasSuccessful() else 1)
