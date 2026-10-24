"""Run static checks, compilation, tests, coverage, and dependency consistency."""
from __future__ import annotations

import os
import subprocess
import sys


def run(*args):
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    run(sys.executable, "-m", "compileall", "-q", ".")
    run("ruff", "check", ".")
    run("pytest", "-m", "not network", "--cov", "--cov-report=term-missing")
    run(sys.executable, "-m", "pip", "check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
