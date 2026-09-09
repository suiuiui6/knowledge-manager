from pathlib import Path
import sys


REPOSITORY_SRC = str((Path(__file__).resolve().parents[1] / "src").resolve())
if sys.path[0] != REPOSITORY_SRC:
    sys.path.insert(0, REPOSITORY_SRC)
