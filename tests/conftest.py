"""Point every test at a throwaway data folder so the suite never writes to the user's real FairScope databases or logs."""
import os
import sys
import tempfile

_ROOT = tempfile.mkdtemp(prefix="fairscope-tests-")
os.environ["LOCALAPPDATA"] = _ROOT
os.environ["XDG_DATA_HOME"] = _ROOT
if sys.platform == "darwin":
    os.environ["HOME"] = _ROOT
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
