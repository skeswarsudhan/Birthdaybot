# Birthday Bot 🎂

Birthday Bot automatically emails employees' managers before their birthday, collects fun facts and photos via a web form, then generates and sends a personalised AI birthday email — all without any human intervention after initial setup. It's designed for a single company (~400 employees) and runs locally on Windows or on PythonAnywhere for demos.

---

## Setup

**Requires Python 3.11+**

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd birthday_bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
copy .env.example .env
```

Open `.env` and fill in these required values:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — free |
| `RESEND_API_KEY` | [resend.com](https://resend.com) — free tier: 3,000 emails/month |
| `FROM_EMAIL` | Any address on a domain verified in Resend |
| `ADMIN_EMAIL` | Your own email address |

### 4. Prepare your employee Excel file

Export your employee list as `employees.xlsx` in the project root.

**Required columns (exact names):**

| Column | Description |
|---|---|
| `Full Name` | Employee display name |
| `Ent ID` | Enterprise ID (e.g. `jsmith`) — used to build email if `Email ID` is absent |
| `Email ID` | Direct email address (optional — preferred over constructed one) |
| `Birthday CurrentYear` | Date in `DD/MM/YYYY` or `MM/DD/YYYY` format |
| `THR/QB` | Department / cost centre |
| `Supervisor` | Manager name in `Lastname, Firstname` format |
| `Supervisor Email` | Manager's email address — **must be populated** |

**Example row:**

| Full Name | Ent ID | Email ID | Birthday CurrentYear | THR/QB | Supervisor | Supervisor Email |
|---|---|---|---|---|---|---|
| Jane Smith | jsmith | jane.smith@accenture.com | 15/08/1990 | Engineering | Doe, John | john.doe@accenture.com |

> **Note:** `Supervisor Email` is the most critical column. Without it, managers won't receive the form link.

A sample `employees.xlsx` with 5 dummy rows is included in the repository.

### 5. Run the bot

```bash
python run.py
```

### 6. Open the dashboard

[http://localhost:8080](http://localhost:8080)

---

## How to get each API key

**Gemini (Google AI Studio)**
1. Visit [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API key"
4. The free tier includes Gemini 1.5 Flash with generous rate limits

**Resend**
1. Visit [resend.com](https://resend.com) and create a free account
2. Go to API Keys → Create API Key
3. Go to Domains → Add Domain, verify your domain's DNS records
4. Set `FROM_EMAIL` to any address on that verified domain
5. Free tier: 3,000 emails/month, 100/day

---

---

## Running the test flow

### Option A: Standalone CLI Test Flow
Verify the entire system works in ~5 minutes without waiting for a real birthday:

```bash
python test_flow.py
```

This will:
1. Create a fake employee with today's birthday.
2. Trigger the birthday scan (`DAYS_BEFORE=0`).
3. Print a manager form URL — open it and submit some fun facts.
4. Send the birthday email to your `ADMIN_EMAIL`.
5. Clean up the test data.

### Option B: E2E Live Test API (Web Server)
You can test the entire workflow with live email sending and immediate birthday email delivery!

1. Start your server:
   ```bash
   python run.py
   ```
2. Trigger the test flow by opening this URL in your browser:
   [http://localhost:8080/api/trigger-test](http://localhost:8080/api/trigger-test)
   
   *(You can customize the emails via query parameters, e.g.: `http://localhost:8080/api/trigger-test?email=eswar@rampp.ai&manager_email=antigravitymapla@gmail.com`)*
   
3. The API will immediately send a **Manager Request Email** to the manager's address and return a JSON response containing the manager form URL (`form_url`).
4. Click the `form_url` in the JSON response, enter fun facts/photos, and submit.
5. Upon submission, Birthday Bot will **immediately** trigger the **Personalized AI Birthday Email** and deliver it directly to the employee's email address in the background.

---

## Deploying to PythonAnywhere

1. **Upload files**: Use the PythonAnywhere file manager or `git clone` in a Bash console
2. **Install dependencies**:
   ```bash
   pip3.11 install --user -r requirements.txt
   ```
3. **Configure .env**: Set `BASE_URL=https://yourusername.pythonanywhere.com`
4. **Verify your domain in Resend**: Add `yourusername.pythonanywhere.com` to Resend's allowed origins (not needed for sending, but the form links must be reachable)
5. **Set up a Web app**:
   - Go to Web tab → Add new web app
   - Choose "Manual configuration" → Python 3.11
   - Set source directory to your project folder
   - Set WSGI file to point to `run.py`'s `app` object:
     ```python
     import sys
     sys.path.insert(0, '/home/yourusername/birthday_bot')
     from web.app import app as application
     ```
6. **Run the scheduler** via an Always-On task (requires paid plan) or a Scheduled task that restarts it daily

> **Note**: The free PythonAnywhere tier does not support Always-On tasks. For a proper demo, use a paid account ($5/month) or keep the scheduler running locally.

---

## Troubleshooting

### Emails going to spam
- Verify your domain in Resend (add SPF, DKIM, DMARC records)
- Make sure `FROM_EMAIL` matches your verified domain exactly
- Check the email preview in Resend's dashboard

### Wrong date format in Excel
- Birthday Bot tries `DD/MM/YYYY` first, then `MM/DD/YYYY`
- If dates are being parsed incorrectly, normalise your Excel column to `DD/MM/YYYY`
- Rows that fail to parse are skipped with a WARNING log

### Token expired
- Tokens are valid until midnight the day after the birthday
- If the manager clicks an old link, they'll see the "Link Expired" page
- Re-run `scan_birthdays_job` manually (or wait for the next day's scan) — it's idempotent

### Gemini rate limit
- The free tier has per-minute limits — if you hit them, the fallback message is used automatically
- Upgrade to a paid Gemini API tier for high-volume use
- The fallback message still uses the employee's name and department

### Photo too large
- Maximum photo size is 2 MB per file
- The form rejects oversized files with a clear error message
- Resize photos before uploading using any image editor

### PythonAnywhere domain not in Resend whitelist
- Resend restricts which domains can be used as `FROM_EMAIL` sender
- You must verify your domain in Resend's dashboard → Domains
- Free accounts support one domain; paid accounts support more
- For demos: use a custom domain (e.g., `birthdaybot.yourdomain.com`) and verify it in Resend
