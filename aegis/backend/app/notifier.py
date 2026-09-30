"""High-risk alerting through AWS SES (email) and/or SNS (topic -> SMS / email / Lambda / Slack).

Runs in "auto" mode by default: live when AWS credentials and a destination are configured,
otherwise dry-run (the full alert is rendered and logged, just not sent). The console shows
which mode is active, so a demo never silently pretends to send mail.
"""
import html
import logging
from typing import Dict, List

from . import config

log = logging.getLogger("aegis.notifier")


class Notifier:
    def __init__(self):
        self._ses = self._sns = None
        self.channels: List[str] = []
        self.mode = "dry-run"
        self.detail = ""
        self.configure()

    def configure(self) -> None:
        want = config.NOTIFY_MODE
        ses_ready = bool(config.SES_FROM and config.SES_TO)
        sns_ready = bool(config.SNS_TOPIC_ARN)
        self.channels = []
        if want in ("auto", "ses", "both") and (ses_ready or want != "auto"):
            self.channels.append("ses")
        if want in ("auto", "sns", "both") and (sns_ready or want != "auto"):
            self.channels.append("sns")
        if not self.channels:
            self.channels = ["ses"]  # still render the email in dry-run so reviewers can see it

        if want == "dry-run":
            self.mode, self.detail = "dry-run", "AEGIS_NOTIFY_MODE=dry-run"
            return
        try:
            import boto3
            session = boto3.Session(region_name=config.AWS_REGION)
            if session.get_credentials() is None:
                self.mode, self.detail = "dry-run", "no AWS credentials found"
                return
            if not (ses_ready or sns_ready):
                self.mode, self.detail = "dry-run", "set AEGIS_SES_FROM/AEGIS_SES_TO or AEGIS_SNS_TOPIC_ARN"
                return
            self._ses = session.client("ses") if "ses" in self.channels else None
            self._sns = session.client("sns") if "sns" in self.channels else None
            self.mode, self.detail = "live", f"region {config.AWS_REGION}"
        except Exception as exc:  # boto3 missing / bad config -> never crash the pipeline
            self.mode, self.detail = "dry-run", f"{type(exc).__name__}: {exc}"
        log.info("notifier mode=%s channels=%s (%s)", self.mode, self.channels, self.detail)

    def status(self) -> dict:
        return {"mode": self.mode, "detail": self.detail, "channels": self.channels,
                "ses_from": config.SES_FROM, "ses_to": config.SES_TO, "sns_topic": config.SNS_TOPIC_ARN,
                "region": config.AWS_REGION, "cooldown_seconds": config.ALERT_COOLDOWN_SECONDS}

    # ------------------------------------------------------------------ rendering
    @staticmethod
    def subject(txn: dict, ev: dict) -> str:
        return (f"[AEGIS {ev['level'].upper()} {ev['score']:.0f}/100] ${txn['amount']:,.2f} at "
                f"{txn['merchant']} - {txn['user_name'] or txn['user_id']}")[:200]

    @staticmethod
    def text_body(txn: dict, ev: dict) -> str:
        lines = [f"AEGIS fraud alert - risk {ev['score']:.0f}/100 ({ev['level']})", "",
                 f"Transaction  {txn['id']}", f"Cardholder   {txn['user_name']} ({txn['user_id']})",
                 f"Amount       ${txn['amount']:,.2f} {txn['currency']}",
                 f"Merchant     {txn['merchant']} [{txn['category']}]",
                 f"Location     {txn['city']}, {txn['country']}", f"Time (UTC)   {txn['ts']}", "",
                 "Why it was flagged:"]
        for h in ev["hits"]:
            lines.append(f"  - [{h['contribution'] * 100:.0f}] {h['rule_name']}: {h['reason']}")
        lines += ["", f"Review: {config.CONSOLE_URL}/?txn={txn['id']}"]
        return "\n".join(lines)

    @staticmethod
    def html_body(txn: dict, ev: dict) -> str:
        e = html.escape
        color = {"critical": "#e5484d", "high": "#f76b15", "medium": "#ffb224"}.get(ev["level"], "#8b8d98")
        rows = "".join(
            f"<tr><td style='padding:8px 10px;border-bottom:1px solid #eee'><b>{e(h['rule_name'])}</b><br>"
            f"<span style='color:#555'>{e(h['reason'])}</span></td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #eee;text-align:right;font-family:monospace'>"
            f"+{h['contribution'] * 100:.0f}</td></tr>" for h in ev["hits"])
        facts = [("Amount", f"${txn['amount']:,.2f} {txn['currency']}"), ("Cardholder", txn["user_name"]),
                 ("Merchant", f"{txn['merchant']} ({txn['category']})"),
                 ("Location", f"{txn['city']}, {txn['country']}"), ("Device", txn["device_id"]),
                 ("Time (UTC)", str(txn["ts"])), ("Transaction", txn["id"])]
        fact_rows = "".join(f"<tr><td style='color:#777;padding:3px 12px 3px 0'>{k}</td><td>{e(str(v))}</td></tr>"
                            for k, v in facts)
        return f"""<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px;margin:auto">
<div style="background:#0b0d12;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0">
<div style="font-size:12px;letter-spacing:2px;opacity:.7">AEGIS FRAUD ALERT</div>
<div style="font-size:26px;font-weight:700;margin-top:4px">Risk <span style="color:{color}">{ev['score']:.0f}/100</span> &middot; {e(ev['level'].upper())}</div>
</div><div style="border:1px solid #e5e5e5;border-top:0;padding:18px 22px;border-radius:0 0 10px 10px">
<table style="font-size:14px;margin-bottom:16px">{fact_rows}</table>
<div style="font-weight:600;margin-bottom:6px">Why AEGIS flagged it</div>
<table style="width:100%;font-size:13px;border-collapse:collapse">{rows}</table>
<a href="{e(config.CONSOLE_URL)}/?txn={e(txn['id'])}" style="display:inline-block;margin-top:18px;background:#0b0d12;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none">Open in Review Console</a>
</div></div>"""

    # ------------------------------------------------------------------ sending
    def send(self, txn: dict, ev: dict) -> List[Dict]:
        """Blocking; call from a worker thread. Returns one record per channel."""
        subject, text = self.subject(txn, ev), self.text_body(txn, ev)
        out = []
        for ch in self.channels:
            rec = {"txn_id": txn["id"], "channel": ch, "mode": self.mode, "subject": subject,
                   "risk_score": ev["score"], "message_id": "", "error": "",
                   "target": ", ".join(config.SES_TO) if ch == "ses" else config.SNS_TOPIC_ARN}
            if self.mode != "live":
                rec["status"] = "simulated"
                log.info("[dry-run %s] %s", ch, subject)
                out.append(rec)
                continue
            try:
                if ch == "ses":
                    resp = self._ses.send_email(
                        Source=config.SES_FROM, Destination={"ToAddresses": config.SES_TO},
                        Message={"Subject": {"Data": subject, "Charset": "UTF-8"},
                                 "Body": {"Text": {"Data": text, "Charset": "UTF-8"},
                                          "Html": {"Data": self.html_body(txn, ev), "Charset": "UTF-8"}}})
                else:
                    resp = self._sns.publish(
                        TopicArn=config.SNS_TOPIC_ARN, Subject=subject[:99], Message=text,
                        MessageAttributes={"risk_level": {"DataType": "String", "StringValue": ev["level"]},
                                           "risk_score": {"DataType": "Number", "StringValue": str(ev["score"])}})
                rec.update(status="sent", message_id=resp.get("MessageId", ""))
            except Exception as exc:
                rec.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                log.error("alert via %s failed: %s", ch, exc)
            out.append(rec)
        return out
