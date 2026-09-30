# Deploy AEGIS live (Render) with real AWS alerts

Total time: about 20 minutes. Everything below is done in your own AWS and Render accounts.
All alert/report emails go to **one** mailbox: `yashwanthmdj@gmail.com`.

## 1. AWS: credentials, SES and SNS (region `ap-south-1`, Mumbai)

Create everything in the **same region** (`ap-south-1`); the region picker is at the top right of the AWS console.

### 1a. An IAM user just for AEGIS
IAM → Users → **Create user** `aegis-alerts` (no console access) → **Attach policies directly** → **Create policy** → JSON:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ses:SendEmail", "ses:GetIdentityVerificationAttributes",
               "sns:Publish", "sns:ListSubscriptionsByTopic"],
    "Resource": "*"
  }]
}
```

Then open the user → **Security credentials** → **Create access key** → "Application running outside AWS".
Keep the Access key ID and Secret access key for step 2. Never commit them to Git.

### 1b. SES email (verify your address)
Amazon SES → **Identities** → **Create identity** → Email address → `yashwanthmdj@gmail.com` → Create.
Open the email AWS sends you and click the verification link. New SES accounts are in the *sandbox*:
they can only send to verified addresses, which is exactly what we want here.

### 1c. SNS topic with an email subscription
Amazon SNS → **Topics** → **Create topic** → Standard → name `aegis-fraud-alerts` → Create.
In the topic → **Create subscription** → Protocol **Email** → Endpoint `yashwanthmdj@gmail.com` → Create.
Open the "AWS Notification - Subscription Confirmation" email and click **Confirm subscription**.
Copy the topic ARN (like `arn:aws:sns:ap-south-1:123456789012:aegis-fraud-alerts`).

## 2. Render: deploy the whole app

1. Push this repository to GitHub (it contains `render.yaml` at the root).
2. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint** → select `Fraud-Rule-Engine`.
3. Render reads `render.yaml` and asks for the three secret values:
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AEGIS_SNS_TOPIC_ARN`. Paste them and **Apply**.
4. The first Docker build takes about 5 minutes. When it's done, open `https://<service>.onrender.com`.
5. In the console: **Alerts** → every check should be green → **Send test alert**.
   One email arrives from SES and one from SNS. **Check the spam folder** the first time and mark it "Not spam".

If a check is red, it says what's wrong. After fixing it (for example, clicking a verification link), press **Re-check AWS**.

## 3. (Optional) Keep the Vercel link working too

The Render URL already serves the full console. To make the existing Vercel frontend use the Render backend:
Vercel project → Settings → Environment Variables → `VITE_API_BASE` = `https://<service>.onrender.com` → Redeploy.

## Before the jury

- The free Render plan **sleeps after 15 minutes of no traffic**. Open the URL 2–3 minutes before presenting.
- The free plan has no persistent disk: the database is re-seeded on every restart/redeploy (fresh demo every time).
- Run locally with real alerts: `cp aegis/.env.example aegis/.env`, fill the keys, `cd aegis && ./run.sh`.

## Live demo script (answers the round-1 questions)

| Question | Show this |
|---|---|
| How is it real-time? | Command Center → **Real-time pipeline**: per-stage timings (~5–10 ms) and the decision mix. Attack Lab → Ingest API console: the response carries `decision` + `stages`. |
| Why wasn't mail sent? | Alerts → pre-flight checks (credentials, SES verification, SNS subscription) → **Send test alert** → show the email on your phone. |
| Two customers, same big spend | Ingest API console: the same amount on a high-spending vs. a low-spending cardholder → **Approve** vs **Hold**. Each is judged against their own baseline. |
| Everyday customer vs. flagged account | Mark one transaction **Confirm fraud** → the next purchase on that account, even a small one, is **Declined** (Account Standing = Compromised). A good customer's big day is only **Held**; after an analyst **Clears** it, a similar amount is **Approved** ("Learned from analyst decision"). |
