import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.mkdtemp()
os.environ.setdefault("AEGIS_DB_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("AEGIS_SIM_AUTOSTART", "0")
os.environ.setdefault("AEGIS_NOTIFY_MODE", "dry-run")
