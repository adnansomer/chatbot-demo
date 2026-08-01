"""Conversation flow engine (see flow.PNG).

    customer reports a problem
              |
        intent analysis  --- general FAQ ---> FAQ knowledge base
              |
       user specific problem
              |
      prompt for MSISDN  <-> send & authenticate OTP
              |
      prompt for location <-> input(location)
              |
      check customer package & balances  -> customer profile
              |
      check_coverage(location)           -> coverage details
              |
      check_site_availability(location)  -> site availability
              |
      derive context & respond -> troubleshooting suggestions
              |
        resolved? -- yes --> close    -- no --> create ticket
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import md
from .faq import FaqIndex, load_index
from .intents import classify_intent, extract_coverage_place, yes_no

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --------------------------------------------------------------------------
# states
# --------------------------------------------------------------------------
S_MENU = "menu"
S_FAQ = "faq"
S_MSISDN = "await_msisdn"
S_OTP = "await_otp"
S_LOCATION = "await_location"
S_COVERAGE = "await_coverage_result"
S_SITE = "await_site_helpful"
S_TICKET = "await_ticket_text"
S_DONE = "done"

FAQ_INDEX: FaqIndex = load_index()


def _further_steps() -> str:
    """Load the 'Recommended Next Steps' block as markdown bullets."""
    path = DATA_DIR / "further-steps.txt"
    if not path.exists():
        return ""
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    bullets = ["📋 **Recommended Next Steps:**", ""]
    for line in lines:
        if not line or line.lower().startswith("recommended next steps"):
            continue
        if ":" in line:
            head, tail = line.split(":", 1)
            bullets.append(f"- **{head.strip()}:**{tail.rstrip()}")
        else:
            bullets.append(f"- {line}")
    return "\n".join(bullets)


FURTHER_STEPS = _further_steps()


# --------------------------------------------------------------------------
# message helpers
# --------------------------------------------------------------------------
def bot(text: str, widgets: list | None = None, meta: bool = False,
        delay: int = 700) -> dict:
    """Build a bot message payload (markdown is rendered server side)."""
    message = {
        "role": "bot",
        "html": md.render(text),
        "widgets": widgets or [],
        "delay": delay,
    }
    if meta:
        message["meta"] = {
            "thinking": random.randint(3, 9),
            "writing": random.randint(2, 8),
        }
    return message


def user(text: str) -> dict:
    return {"role": "user", "text": text}


def field_widget(name: str, placeholder: str = "", prefix: str = "",
                 maxlength: int = 64, inputmode: str = "text") -> dict:
    return {
        "type": "field",
        "name": name,
        "label": name,
        "prefix": prefix,
        "placeholder": placeholder,
        "maxlength": maxlength,
        "inputmode": inputmode,
    }


TICKET_FORM = {
    "type": "ticket_form",
    "label": "Your Ticket Message",
    "placeholder": "Please describe your issue in your own words…",
    "maxlength": 500,
}


def map_pin_widget(address: str) -> dict:
    return {
        "type": "map_pin",
        "address": address,
        "caption": "Shared location • Tap to open in Maps",
    }


STREET_NAMES = [
    "Western Service Road", "Rivonia Road", "Jan Smuts Avenue",
    "Church Street", "Voortrekker Road", "Main Reef Road",
    "Beyers Naude Drive", "Witkoppen Road", "Bram Fischer Drive",
    "Malibongwe Drive", "Kelvin Drive", "Republic Road",
]


def fake_address(location: str) -> str:
    """Deterministic fake street address used for the mocked map pin."""
    rng = random.Random("addr:" + location.lower())
    number = rng.randint(1, 220)
    street = rng.choice(STREET_NAMES)
    return f"{number} {street}, {location}"


# --------------------------------------------------------------------------
# fake backend systems (package/balance, coverage, site availability)
# --------------------------------------------------------------------------
@dataclass
class Session:
    session_id: str
    state: str = S_MENU
    msisdn: str = ""
    otp: str = ""
    otp_attempts: int = 0
    location: str = ""
    profile: dict = field(default_factory=dict)
    ticket_id: str = ""


PLANS = [
    ("FreeMe 40GB", 40.0),
    ("FreeMe 25GB", 25.0),
    ("SmartBroadband Wireless 40GB", 40.0),
]


def build_profile(msisdn: str) -> dict:
    """Deterministic mock customer profile for a given MSISDN."""
    rng = random.Random(msisdn)
    plan_name, total = rng.choice(PLANS)
    used = round(rng.uniform(0.18, 0.42) * total, 1)
    remaining = round(total - used, 1)
    night_total = total
    night_remaining = round(night_total - rng.uniform(0.5, 4.0), 1)
    today = datetime.now()
    # last day of the current month
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    expiry = next_month - timedelta(days=1)
    return {
        "plan": plan_name,
        "status": "Active",
        "total_gb": total,
        "used_gb": used,
        "remaining_gb": remaining,
        "night_total_gb": night_total,
        "night_remaining_gb": night_remaining,
        "airtime": round(rng.uniform(45, 320), 2),
        "expiry": expiry.strftime("%d %B %Y"),
        "percent_left": int(round(remaining / total * 100)),
    }


def format_msisdn(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    digits = digits.lstrip("0")
    return "0" + digits


def mask_msisdn(msisdn: str) -> str:
    if len(msisdn) < 6:
        return msisdn
    # '•' rather than '*' so the mask never collides with markdown emphasis
    return msisdn[:3] + "•" * (len(msisdn) - 5) + msisdn[-2:]


# --------------------------------------------------------------------------
# canned copy
# --------------------------------------------------------------------------
GREETING = (
    "Good day! Thank you for reaching out to **Telkom SA Digital Assistant**. 💙\n"
    "\n"
    "How can I assist you today? You can ask me a general question about our "
    "products, services, store locations and pricing, or tell me about a "
    "problem you're having with your own line — for example *\"my internet "
    "was bad today\"* — and I'll run a full network check for you.\n"
    "\n"
    "Just type your message below to get started."
)

OTP_PROMPT = (
    "I noticed you are not logged in yet. Please complete the OTP login to "
    "proceed by entering your Telkom line number, e.g. 0-125551234"
)

RESOLVED_CLOSING = (
    "Wonderful — I am glad that resolved it! 🎉\n"
    "\n"
    "Thank you for choosing Telkom 💙. Your line is now connected to the best "
    "available network technology in your area. If anything changes, you can "
    "come back to me at any time.\n"
    "\n"
    "Have a great day!"
)

FINAL_CLOSING = (
    "If you need any other assistance with your Telkom services, please don't "
    "hesitate to reach out. Have a great day!"
)


TECH_NOTES = {
    "5G": "Ultra-fast 5G broadband with the lowest latency on our network.",
    "4G LTE": "High-speed 4G LTE / LTE-Advanced mobile data.",
    "3G": "Standard 3G voice and data.",
    "2G": "Basic 2G voice and SMS.",
}


def adhoc_coverage_report(location: str) -> tuple[list[str], bool, str, str]:
    """Deterministic fake coverage result for an ad-hoc lookup."""
    rng = random.Random("coverage-lookup:" + location.lower())
    techs = ["2G"]
    if rng.random() < 0.93:
        techs.append("3G")
    if rng.random() < 0.9:
        techs.append("4G LTE")
    has_5g = rng.random() < 0.6
    if has_5g:
        techs.append("5G")
    strength = rng.choices(["Excellent", "Good", "Fair"], weights=[45, 40, 15])[0]
    bars = {"Excellent": "🟩🟩🟩🟩", "Good": "🟩🟩🟩⬜", "Fair": "🟩🟩⬜⬜"}[strength]
    return techs, has_5g, strength, bars


def adhoc_coverage_message(location: str) -> str:
    techs, has_5g, strength, bars = adhoc_coverage_report(location)
    tech_lines = "\n".join(f"- **{t}** — {TECH_NOTES[t]}" for t in techs)
    headline = "🎉 Great news" if has_5g else "📶 Good news"
    five_g_line = (
        f"5G broadband is available in {location} on compatible devices and "
        "packages."
        if has_5g else
        f"5G is not yet available in {location}, but our 4G LTE network "
        "delivers strong speeds in the meantime — we're continuously "
        "expanding our 5G footprint."
    )
    return (
        f"📡 **Coverage check — {location}**\n"
        "\n"
        f"{headline}! Here's what our network records show for this area:\n"
        "\n"
        f"- **Signal strength:** {strength} {bars}\n"
        f"- **Available technologies:**\n{tech_lines}\n"
        "\n"
        f"{five_g_line}\n"
        "\n"
        "Would you like me to check coverage somewhere else, or is there a "
        "specific problem with your own line I can help troubleshoot?"
    )


def coverage_message(location: str) -> str:
    return (
        f"📡 **Coverage check completed — {location}**\n"
        "\n"
        f"Good news! Our network records show that **5G is now live in "
        f"{location}**, in addition to our LTE / LTE-Advanced layer. Your SIM "
        "and your current package are both 5G enabled, but your handset may "
        "still be locked to an older network mode, which would explain the "
        "slow speeds you are experiencing.\n"
        "\n"
        "📱 **Could you please check your phone settings?**\n"
        "\n"
        "- **Android:** Settings → Connections → Mobile networks → Network "
        "mode → select **5G/LTE/3G/2G (auto connect)**\n"
        "- **iPhone:** Settings → Mobile Data → Mobile Data Options → Voice & "
        "Data → select **5G Auto**\n"
        "- Toggle flight mode on for 10 seconds and off again so the device "
        "re-registers on the strongest cell\n"
        "\n"
        "Once you have done that, did your connection improve?"
    )


def package_message(profile: dict, location: str) -> str:
    return (
        "✅ **Package & Balance check completed**\n"
        "\n"
        f"- **Package:** {profile['plan']} ({profile['status']})\n"
        f"- **Anytime data remaining:** {profile['remaining_gb']} GB of "
        f"{profile['total_gb']} GB ({profile['percent_left']}% left)\n"
        f"- **Used this month:** {profile['used_gb']} GB\n"
        f"- **Night Surfer data remaining:** {profile['night_remaining_gb']} GB "
        f"of {profile['night_total_gb']} GB (usable 12am–6am)\n"
        f"- **Airtime balance:** R{profile['airtime']:.2f}\n"
        f"- **Bundle valid until:** {profile['expiry']}\n"
        "\n"
        "💡 **What this tells us:** your bundle is active and you still have "
        f"{profile['remaining_gb']} GB of anytime data available, so there is "
        "**no depletion, no spend limit and no suspension** on your account. "
        "This is not a billing or bundle issue.\n"
        "\n"
        f"Let me now check the network coverage in **{location}**…"
    )


def site_status_message(location: str, reference: str) -> str:
    return (
        f"🛠️ **Site availability check completed — {location}**\n"
        "\n"
        "Thank you for confirming. I have now queried the sites serving your "
        f"area and I can see the cause of the problem: **planned network "
        f"upgrade work is currently in progress on the site that serves "
        f"{location}**.\n"
        "\n"
        f"- **Work reference:** {reference}\n"
        f"- **Affected area:** {location} and immediate surroundings\n"
        "- **Impact:** reduced throughput, intermittent connectivity and "
        "short interruptions during switch-over windows\n"
        "- **Expected restoration:** within the next 24–48 hours\n"
        "\n"
        "Our engineering teams are upgrading the capacity on this site, which "
        "means your experience will be noticeably better once the work is "
        "completed. I sincerely apologise for the inconvenience in the "
        "meantime."
    )


def troubleshooting_message() -> str:
    return (
        "🔧 **What you can do while the work is in progress:**\n"
        "\n"
        "1. 🔄 **Restart your connection** — Switch flight mode on for 30 "
        "seconds and off again so your device registers on the strongest "
        "neighbouring cell.\n"
        "2. 📶 **Check your signal strength** — If you have fewer than two "
        "bars, move to a different room or closer to a window.\n"
        "3. 🧭 **Reposition your router** — Keep it elevated, central and away "
        "from thick walls, mirrors and other electronics.\n"
        "4. 🔌 **Test with one device** — Disconnect other devices briefly to "
        "confirm whether the slowdown is on the network or on your home "
        "network.\n"
        "5. ⏱️ **Try off-peak hours** — Test your speed early morning or late "
        "evening to see if congestion is the cause.\n"
        "6. 🛠️ **Update your equipment** — Ensure your router firmware and "
        "device software are up-to-date.\n"
        "\n"
        f"{FURTHER_STEPS}\n"
        "\n"
        "If the issue continues after trying these steps, please let us know:\n"
        "\n"
        "- **Which devices** are experiencing slow speeds?\n"
        "- **What time of day** it usually happens?\n"
        "- **Whether you're using Wi-Fi or a direct cable connection?**\n"
        "\n"
        "🤝 **Closing:**\n"
        "Thank you for staying connected with Telkom 💙. We're here to help "
        "you get the best possible experience.\n"
        "\n"
        "Did these suggestions resolve your issue?"
    )


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
class FlowEngine:
    def __init__(self):
        self.sessions: dict[str, Session] = {}

    # -- session -----------------------------------------------------------
    def session(self, session_id: str) -> Session:
        s = self.sessions.get(session_id)
        if s is None:
            s = Session(session_id=session_id)
            self.sessions[session_id] = s
        return s

    def reset(self, session_id: str) -> list[dict]:
        self.sessions[session_id] = Session(session_id=session_id)
        return self.start(session_id)

    def start(self, session_id: str) -> list[dict]:
        s = self.session(session_id)
        s.state = S_MENU
        return [bot(GREETING, delay=300)]

    # -- entry points ------------------------------------------------------
    def handle_text(self, session_id: str, text: str) -> list[dict]:
        s = self.session(session_id)
        text = (text or "").strip()
        if not text:
            return []

        # Ad-hoc "do you have coverage in X?" lookups work at any point in
        # the conversation, without needing to log in first, and don't
        # disturb whatever step the user was already on.
        place = extract_coverage_place(text)
        if place:
            return self._adhoc_coverage_check(s, place)

        state = s.state

        if state == S_MSISDN:
            return self._submit_msisdn(s, text)
        if state == S_OTP:
            return self._submit_otp(s, text)
        if state == S_LOCATION:
            return self._submit_location(s, text)
        if state == S_TICKET:
            return self._submit_ticket(s, text)
        if state == S_COVERAGE:
            return self._coverage_answer(s, text)
        if state == S_SITE:
            return self._site_answer(s, text)
        if state == S_DONE:
            return self._after_done(s, text)

        # menu / faq -> intent analysis
        if classify_intent(text) == "network":
            return self._start_troubleshooting(s)
        return self._answer_faq(s, text)

    def handle_action(self, session_id: str, action: str, value: str = "",
                      name: str = "") -> list[dict]:
        s = self.session(session_id)

        if action == "field":
            if name == "phone_number":
                return self._submit_msisdn(s, value)
            if name == "customer_input_ver_code":
                return self._submit_otp(s, value)
            if name == "location":
                return self._submit_location(s, value)
            if name == "ticket_description":
                return self._submit_ticket(s, value)
        if action == "open_ticket":
            return self._open_ticket_form(s)
        return []

    # -- ad-hoc coverage lookup ---------------------------------------------
    def _adhoc_coverage_check(self, s: Session, place: str) -> list[dict]:
        location = re.sub(r"\s+", " ", place.strip())[:60].title()
        address = fake_address(location)
        messages = [
            bot(f"Sure — let me check that for you. Pinning **{location}** "
                f"on the map…", [map_pin_widget(address)], delay=600),
            bot(adhoc_coverage_message(location), meta=True, delay=1200),
        ]
        messages.extend(self._reprompt(s))
        return messages

    def _reprompt(self, s: Session) -> list[dict]:
        """Remind the user what we were waiting for, without restarting it -
        used after an ad-hoc question interrupts an in-progress step."""
        if s.state == S_MSISDN:
            return [bot(
                "Whenever you're ready, please enter your Telkom line "
                "number to continue your network check.",
                [field_widget("phone_number", placeholder="123456789",
                              prefix="0-", maxlength=10,
                              inputmode="numeric")], delay=500)]
        if s.state == S_OTP:
            return [bot(
                "Whenever you're ready, please input the verification_code "
                "I sent you earlier to continue.",
                [field_widget("customer_input_ver_code", placeholder=s.otp,
                              maxlength=4, inputmode="numeric")], delay=500)]
        if s.state == S_LOCATION:
            return [bot(
                "Whenever you're ready, please enter the town, suburb or "
                "area that is affected so I can continue your network "
                "check.",
                [field_widget("location", placeholder="e.g. Centurion, Pretoria",
                              maxlength=60)], delay=500)]
        if s.state == S_COVERAGE:
            return [bot(
                "So, back to your line — did checking your network mode "
                "settings resolve the problem?", delay=500)]
        if s.state == S_SITE:
            return [bot(
                "So, back to your line — did these suggestions resolve "
                "your issue?", delay=500)]
        if s.state == S_TICKET:
            return [bot(
                "Whenever you're ready, please describe your original "
                "issue (maximum 500 characters) so I can log the ticket.",
                [TICKET_FORM], delay=500)]
        return []

    # -- FAQ ---------------------------------------------------------------
    def _answer_faq(self, s: Session, text: str) -> list[dict]:
        s.state = S_FAQ
        entry, score, suggestions = FAQ_INDEX.best(text)
        if entry is not None:
            return [bot(entry.answer, meta=True, delay=600)]

        if suggestions:
            listing = "\n".join(
                f"{i}. {e.question}" for i, e in enumerate(suggestions, 1))
            hint = ("\n\nYou can rephrase your question, or type one of the "
                    f"topics above:\n\n{listing}")
        else:
            hint = ""
        return [bot(
            "I could not find a confident answer to that in our knowledge "
            "base yet. 🤔\n"
            "\n"
            "You can rephrase your question, or visit **www.telkom.co.za** "
            "for the latest information. If you are experiencing a problem "
            "with your own line or data connection, just tell me — for "
            "example *\"my internet is very slow today\"* — and I will run "
            f"a full network check for you.{hint}",
            delay=600)]

    # -- troubleshooting ---------------------------------------------------
    def _start_troubleshooting(self, s: Session) -> list[dict]:
        s.state = S_MSISDN
        s.otp_attempts = 0
        return [
            bot("I'm sorry to hear you are experiencing trouble with your "
                "connection. 😔 Let's get to the bottom of it together — I "
                "will run a full check on your line.", delay=400),
            bot(OTP_PROMPT,
                [field_widget("phone_number", placeholder="123456789",
                              prefix="0-", maxlength=10, inputmode="numeric")],
                delay=900),
        ]

    def _submit_msisdn(self, s: Session, raw: str) -> list[dict]:
        digits = re.sub(r"\D", "", raw or "")
        if len(digits.lstrip("0")) < 8 or len(digits) > 11:
            return [bot("That number doesn't look quite right. Please enter "
                        "your 9-digit Telkom line number after the 0, "
                        "e.g. 0-125551234",
                        [field_widget("phone_number", placeholder="123456789",
                                      prefix="0-", maxlength=10,
                                      inputmode="numeric")], delay=500)]
        s.msisdn = format_msisdn(digits)
        s.otp = f"{random.randint(1000, 9999)}"
        s.state = S_OTP
        return [bot(
            f"Your verification code is {s.otp}.\n"
            "\n"
            "Please input your verification_code.",
            [field_widget("customer_input_ver_code", placeholder=s.otp,
                          maxlength=4, inputmode="numeric")], delay=900)]

    def _submit_otp(self, s: Session, raw: str) -> list[dict]:
        code = re.sub(r"\D", "", raw or "")
        if code != s.otp:
            s.otp_attempts += 1
            if s.otp_attempts >= 3:
                s.otp = f"{random.randint(1000, 9999)}"
                s.otp_attempts = 0
                return [bot(
                    "For your security I have generated a new code.\n"
                    "\n"
                    f"Your verification code is {s.otp}.\n"
                    "\n"
                    "Please input your verification_code.",
                    [field_widget("customer_input_ver_code",
                                  placeholder=s.otp, maxlength=4,
                                  inputmode="numeric")], delay=600)]
            return [bot(
                "That verification code is incorrect. Please try again — the "
                f"code sent to {mask_msisdn(s.msisdn)} is 4 digits long.",
                [field_widget("customer_input_ver_code", placeholder="••••",
                              maxlength=4, inputmode="numeric")], delay=500)]

        s.state = S_LOCATION
        return [
            bot(f"✅ Thank you, you are now securely logged in with "
                f"**{mask_msisdn(s.msisdn)}**.", delay=500),
            bot("To check the network correctly I need to know where you are "
                "experiencing the problem.\n"
                "\n"
                "Please enter the town, suburb or area that is affected.",
                [field_widget("location", placeholder="e.g. Centurion, Pretoria",
                              maxlength=60)], delay=900),
        ]

    def _submit_location(self, s: Session, raw: str) -> list[dict]:
        location = re.sub(r"\s+", " ", (raw or "").strip())[:60]
        if len(location) < 2:
            return [bot("I did not quite catch that. Please enter the town, "
                        "suburb or area that is affected.",
                        [field_widget("location",
                                      placeholder="e.g. Centurion, Pretoria",
                                      maxlength=60)], delay=500)]
        s.location = location.title()
        s.profile = build_profile(s.msisdn)
        s.state = S_COVERAGE
        address = fake_address(s.location)
        return [
            bot("Thanks — pinning your location on the map now…",
                [map_pin_widget(address)], delay=600),
            bot("Before we look at the network itself, let me check your "
                "package and balances first — a depleted bundle or a spend "
                "limit can look exactly like a network fault. One moment "
                "please…", delay=800),
            bot(package_message(s.profile, s.location), meta=True, delay=1400),
            bot(coverage_message(s.location), meta=True, delay=1600),
        ]

    def _coverage_answer(self, s: Session, text: str) -> list[dict]:
        answer = yes_no(text)
        if answer == "yes":
            s.state = S_DONE
            return [bot(RESOLVED_CLOSING, meta=True, delay=700)]
        if answer == "no":
            s.state = S_SITE
            reference = "NW-" + "".join(random.choice("0123456789")
                                        for _ in range(6))
            return [
                bot(f"Thank you for checking. Since the network mode is "
                    f"already correct, let me look deeper and check the site "
                    f"availability for **{s.location}**…", delay=600),
                bot(site_status_message(s.location, reference), meta=True,
                    delay=1400),
                bot(troubleshooting_message(), meta=True, delay=1800),
            ]
        return [bot("Sorry, I didn't catch that — please reply with **yes** "
                    "or **no**. Did checking your network mode settings "
                    "resolve the problem?", delay=500)]

    def _site_answer(self, s: Session, text: str) -> list[dict]:
        answer = yes_no(text)
        if answer == "yes":
            s.state = S_DONE
            return [bot(FINAL_CLOSING, meta=True, delay=700)]
        if answer == "no":
            return self._open_ticket_form(s)
        return [bot("Sorry, I didn't catch that — please reply with **yes** "
                    "or **no**. Did these suggestions resolve your issue?",
                    delay=500)]

    def _open_ticket_form(self, s: Session) -> list[dict]:
        s.state = S_TICKET
        return [bot(
            "No problem at all — I will log a support ticket so that our "
            "technical team can investigate your line directly. 📝\n"
            "\n"
            "Please describe the issue in your own words (maximum 500 "
            "characters) and press Enter to submit it.",
            [TICKET_FORM], delay=600)]

    def _submit_ticket(self, s: Session, raw: str) -> list[dict]:
        description = (raw or "").strip()[:500]
        if len(description) < 3:
            return [bot("Please add a short description of the issue "
                        "(maximum 500 characters) so our technical team knows "
                        "what to investigate.", [TICKET_FORM], delay=400)]
        s.ticket_id = "TKT" + "".join(random.choice("0123456789")
                                      for _ in range(8))
        created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        s.state = S_DONE
        return [bot(
            "Dear , The ticket has been successfully created 🎉 You can reach "
            "the ticket information below.\n"
            "\n"
            f"Ticket Creation Time: {created} Ticket ID: {s.ticket_id}\n"
            "\n"
            "We will get back to you as soon as possible with news of a "
            "resolution.",
            meta=True, delay=1500)]

    def _after_done(self, s: Session, text: str) -> list[dict]:
        """The journey is finished - fall back to intent analysis again."""
        if classify_intent(text) == "network":
            return self._start_troubleshooting(s)
        return self._answer_faq(s, text)


engine = FlowEngine()
