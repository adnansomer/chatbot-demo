# Telkom SA Digital Assistant

A web chatbot that reproduces the Telkom assistant UI and implements the
network-troubleshooting flow. All conversation content is in English.

## Run locally (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Flask app factory + JSON API (`/api/start`, `/api/message`, `/api/action`, `/api/reset`) |
| `chatbot/flow.py` | The conversation state machine (the whole flow diagram) |
| `chatbot/faq.py` | FAQ parsing + TF-IDF style retrieval over `data/faq.txt` |
| `chatbot/intents.py` | Intent analysis (`faq` vs `network`) and yes/no detection |
| `chatbot/md.py` | Small markdown → HTML renderer used for bot messages |
| `data/faq.txt` | Knowledge base, `QuestionN:` / `AnswerN:` format |
| `data/further-steps.txt` | "Recommended Next Steps" block used by the site-availability reply |
| `templates/index.html`, `static/` | The UI (no build step, vanilla JS) |
| `deploy/` | gunicorn / systemd / nginx files for the ECS deployment |

## Conversation flow

```
customer message
   └── intent analysis
        ├── general FAQ ─────────► answer from data/faq.txt
        └── user specific problem
             ├── prompt for MSISDN  ↔ send & authenticate OTP (4-digit, shown on screen for testing)
             ├── prompt for location
             ├── check customer package & balances  → balance is sufficient, so not a bundle issue
             ├── check_coverage(location)           → "5G is live in your area, check your phone settings"
             │      ├── resolved  → thank-you closing
             │      └── not resolved ↓
             ├── check_site_availability(location)  → planned technical work on the serving site
             ├── troubleshooting suggestions + recommended next steps
             └── helpful?
                  ├── yes → "If you need any other assistance … Have a great day!"
                  └── no  → Create Ticket → 500-character description → ticket ID + creation time
```

Notes:

* The OTP is **displayed in the chat** on purpose — this is a test build, there
  is no SMS gateway wired up.
* Customer profile, coverage and site-availability results are mocked in
  `chatbot/flow.py` (`build_profile`, `coverage_message`, `site_message`).
  Replace those three functions with real API calls when the back-end systems
  are available.
* Conversation state lives in memory (`FlowEngine.sessions`), keyed by a
  browser-generated session id. Restarting the server clears all conversations.

### Ad-hoc coverage lookups

At any point in the conversation — logged in or not, mid-FAQ or mid-flow —
a message matching "do you have coverage in X", "is X covered", "coverage in
X", "5G in X" etc. is intercepted by `extract_coverage_place()`
(`chatbot/intents.py`) and answered immediately with a fake map pin
(`map_pin_widget`) plus a fake coverage report (`adhoc_coverage_message` in
`chatbot/flow.py`), without disturbing whatever step the user was on. If they
were mid-step (e.g. waiting for an OTP or a ticket description), the engine
re-prompts the same field afterwards (`FlowEngine._reprompt`) so the original
task resumes exactly where it left off.

## Adding or editing FAQ content

Edit `data/faq.txt` and keep the `QuestionN:` / `AnswerN:` structure. Answers
support a markdown subset: `**bold**`, `- bullets`, `1. numbered lists`, pipe
tables and `[links](url)`. Restart the server to reload.

For questions customers phrase very differently, add extra keywords to
`ALIASES` in `chatbot/faq.py`.

## Deploy to a Huawei Cloud ECS

On the ECS (Ubuntu/EulerOS, Python 3.11+):

```bash
sudo useradd -r -m -d /opt/telkom-chatbot telkom
sudo mkdir -p /var/log/telkom-chatbot && sudo chown telkom: /var/log/telkom-chatbot

# copy the project to /opt/telkom-chatbot, then:
cd /opt/telkom-chatbot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

sudo cp deploy/telkom-chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telkom-chatbot

sudo cp deploy/nginx.conf /etc/nginx/conf.d/telkom-chatbot.conf
sudo nginx -t && sudo systemctl reload nginx
```

Then open port 80 (and 443 if you add TLS) in the ECS **security group**, and
point the EIP or domain at the instance. `GET /healthz` returns
`{"status":"ok"}` for the load balancer health check.

Because conversation state is per-process, run a single gunicorn worker or
enable session affinity if you put an ELB in front of several instances.
