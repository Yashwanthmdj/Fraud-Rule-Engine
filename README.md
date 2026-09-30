# AEGIS - fraud rule engine 🚀

**A real-time fraud rule engine with a live investigation console.** AEGIS scores transactions, explains the signals behind each decision, and lets analysts review cases and test rule changes.

> AEGIS is a demonstration project. It uses simulated cardholders and synthetic transactions; it is not a production-certified fraud or payment-processing system.

## Start AEGIS

Requirements: Python 3.9+, Node.js 18+, and npm.

Run these commands from the project folder, the one containing `run.sh`. In this workspace, first enter that folder with `cd aegis`.

```bash
./run.sh
```

On first run, the script installs dependencies and builds the web console. Open **http://localhost:8000** when the server starts. API documentation is at **http://localhost:8000/docs**.

To stop the server, press `Ctrl+C` in its terminal. To clear the local database and reseed demo data, run:

```bash
./run.sh --reset
```

## What you can do

- **Monitor transactions:** View live traffic, risk indicators, and transaction locations in the Command Center.
- **Review cases:** Inspect evidence, record a verdict, and see the audit history in the Review Queue.
- **Test fraud scenarios:** Generate controlled attacks from the Attack Lab.
- **Tune detection:** Change rule weights and parameters, then backtest before applying changes in the Rules Lab.
- **Add rules:** Drop a Python plugin into `backend/app/rules/`; the engine discovers it without a restart.
- **Send alerts:** Use AWS SES or SNS for critical events. Notifications run in dry-run mode by default.

## How scoring works

Each rule returns a confidence value from 0 to 1. AEGIS multiplies that value by the rule's weight, then combines the rule signals with noisy-OR fusion:

```text
contribution = min(1, confidence * weight)
risk = 100 * (1 - product(1 - contribution))
```

Multiple warning signs can raise the total risk together. By default, scores below 35 are low, scores from 35 to 79 are flagged for review, and scores of 80 or higher are critical. Thresholds can be changed in the Rules Lab.

## Run with Docker

From the project folder:

```bash
docker build -t aegis .
docker run --rm -p 8000:8000 aegis
```

Docker runs in dry-run alert mode by default, so a `.env` file is not required. To configure AWS alerts, copy `.env.example` to `.env`, add your settings, and pass it to the container:

```bash
cp .env.example .env
docker run --rm -p 8000:8000 --env-file .env aegis
```

## Development mode

Run `./run.sh` once to install backend and frontend dependencies, then stop it with `Ctrl+C`. Start the backend and frontend in separate terminals, with both terminals opened in the project folder.

Backend:

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** for the frontend. It proxies API and WebSocket requests to the backend on port 8000.

## Built-in rules

| Rule | What it detects |
|---|---|
| Velocity | Unusually frequent transactions and card-testing patterns |
| Amount anomaly | Amounts that differ from a cardholder's normal spending |
| Impossible travel | Transactions too far apart to be explained by normal travel |
| Unrecognized device | Devices not previously associated with a cardholder |
| High-risk merchant | Transactions involving categories such as gift cards or crypto |

Transaction history used for scoring is limited to events before the transaction being evaluated. This avoids using future data during scoring and backtests.

## Add a rule

Create a Python file in `backend/app/rules/`. A rule subclasses `Rule` and returns a `RuleResult` when its condition matches. See [`examples/foreign_cashout.py`](examples/foreign_cashout.py) for a complete example. The rules watcher loads new plugins automatically.

## AWS alerts

Alerts are logged locally in dry-run mode. To enable SES or SNS notifications:

1. Copy `.env.example` to `.env`.
2. Set the required AWS and AEGIS notification values, including `AEGIS_SES_FROM` and `AEGIS_SES_TO` for email.
3. Start AEGIS with `./run.sh`, or pass `.env` to Docker with `--env-file .env`.

Never commit `.env` or AWS credentials. AWS permissions may include `ses:SendEmail` and `sns:Publish`, depending on which notification services you configure.

## API and tests

Interactive API documentation is available at **http://localhost:8000/docs** while the backend is running. The API supports transaction scoring and search, case reviews, rule configuration, backtesting, attack scenarios, notifications, and live WebSocket events.

Run the backend tests from the project folder:

```bash
cd backend
.venv/bin/python -m pytest -q
```

## Project layout

```text
backend/app/      API, scoring engine, rules, simulator, and notifications
frontend/         React review console
examples/         Example rule plugins
run.sh            Install, build, and start AEGIS
```
