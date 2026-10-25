"""Point every test at a throwaway data folder so the suite never writes to the user's real FairScope databases or logs."""
import os
import sys
import tempfile

_ROOT = tempfile.mkdtemp(prefix="fairscope-tests-")
os.environ["LOCALAPPDATA"] = _ROOT
os.environ["XDG_DATA_HOME"] = _ROOT
if sys.platform == "darwin":
    os.environ["HOME"] = _ROOT
# Never touch the real OS keychain: on macOS CI (HOME moved above) it waits forever for an unlock prompt; the app falls back to its key file.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
