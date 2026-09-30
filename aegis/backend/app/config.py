"""Runtime configuration. Everything is overridable through environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = Path(os.getenv("AEGIS_RULES_DIR", Path(__file__).resolve().parent / "rules"))
DB_URL = os.getenv("AEGIS_DB_URL", f"sqlite:///{BASE_DIR / 'aegis.db'}")
FRONTEND_DIST = Path(os.getenv("AEGIS_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

# Risk thresholds (0-100). Editable live from the console; these are just the boot defaults.
FLAG_THRESHOLD = float(os.getenv("AEGIS_FLAG_THRESHOLD", 35))
ALERT_THRESHOLD = float(os.getenv("AEGIS_ALERT_THRESHOLD", 80))

# Notifications: "auto" = go live if AWS credentials + a destination exist, otherwise dry-run.
NOTIFY_MODE = os.getenv("AEGIS_NOTIFY_MODE", "auto")  # auto | ses | sns | both | dry-run
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
SES_FROM = os.getenv("AEGIS_SES_FROM", "")
SNS_TOPIC_ARN = os.getenv("AEGIS_SNS_TOPIC_ARN") or os.getenv("AWS_SNS_TOPIC_ARN", "")
ALERT_COOLDOWN_SECONDS = int(os.getenv("AEGIS_ALERT_COOLDOWN", 90))
# Render sets RENDER_EXTERNAL_URL automatically, so alert links point at the live console.
CONSOLE_URL = os.getenv("AEGIS_CONSOLE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000"

# The single demo cardholder. Every alert/report goes to one reviewer mailbox (AEGIS_SES_TO,
# falling back to this address) - never to the simulated customers.
DEMO_USER_ID = os.getenv("AEGIS_DEMO_USER_ID", "C-DEMO-001")
DEMO_USER_NAME = os.getenv("AEGIS_DEMO_USER_NAME", "Yashwanth M (Demo)")
DEMO_EMAIL = os.getenv("AEGIS_DEMO_EMAIL", "")
DEMO_BANK = os.getenv("AEGIS_DEMO_BANK", "SBI")
SES_TO = [e.strip() for e in (os.getenv("AEGIS_SES_TO") or DEMO_EMAIL).split(",") if e.strip()]

# Simulator
SIM_AUTOSTART = os.getenv("AEGIS_SIM_AUTOSTART", "1") == "1"
SIM_RATE = float(os.getenv("AEGIS_SIM_RATE", 1.2))  # transactions / second
