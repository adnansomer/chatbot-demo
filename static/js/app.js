/* =========================================================================
   Telkom SA Digital Assistant — front-end
   ========================================================================= */
(function () {
  "use strict";

  const appEl = document.getElementById("app");
  const chatEl = document.getElementById("chat");
  const listEl = document.getElementById("messages");
  const inputEl = document.getElementById("composer-input");
  const sendEl = document.getElementById("send-btn");
  const homeEl = document.getElementById("home-btn");
  const landingInputEl = document.getElementById("landing-input");
  const landingSendEl = document.getElementById("landing-send-btn");
  const suggestionCards = document.querySelectorAll(".suggestion-card");

  const botAvatarTpl = document.getElementById("tpl-bot-avatar");
  const userAvatarTpl = document.getElementById("tpl-user-avatar");
  const shimmerTpl = document.getElementById("tpl-shimmer");

  let busy = false;

  /* ---------------------------------------------------------- session -- */
  function sessionId() {
    let id = sessionStorage.getItem("tk_session_id");
    if (!id) {
      id = "s-" + Math.random().toString(36).slice(2) + "-" + Date.now().toString(36);
      sessionStorage.setItem("tk_session_id", id);
    }
    return id;
  }

  async function post(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ session_id: sessionId() }, payload)),
    });
    if (!res.ok) throw new Error("Request failed: " + res.status);
    return res.json();
  }

  /* ------------------------------------------------------------ utils -- */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function scrollToBottom(smooth) {
    requestAnimationFrame(() => {
      chatEl.scrollTo({ top: chatEl.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    });
  }

  function avatar(role) {
    const tpl = role === "bot" ? botAvatarTpl : userAvatarTpl;
    return tpl.content.firstElementChild.cloneNode(true);
  }

  function makeRow(role) {
    const row = document.createElement("div");
    row.className = "row " + role;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "bot") {
      row.appendChild(avatar("bot"));
      row.appendChild(bubble);
    } else {
      row.appendChild(bubble);
      row.appendChild(avatar("user"));
    }
    return { row, bubble };
  }

  /* -------------------------------------------------------- rendering -- */
  function addUserMessage(text) {
    const { row, bubble } = makeRow("user");
    const p = document.createElement("p");
    p.textContent = text;
    bubble.appendChild(p);
    listEl.appendChild(row);
    scrollToBottom(true);
  }

  function showTyping() {
    const row = document.createElement("div");
    row.className = "row bot typing";
    row.appendChild(avatar("bot"));
    row.appendChild(shimmerTpl.content.firstElementChild.cloneNode(true));
    listEl.appendChild(row);
    scrollToBottom(true);
    return row;
  }

  function addBotMessage(msg) {
    const { row, bubble } = makeRow("bot");
    bubble.innerHTML = msg.html || "";

    if (msg.meta) {
      const meta = document.createElement("div");
      meta.className = "msg-meta";
      meta.innerHTML =
        "<span>🧠 Thinking: " + msg.meta.thinking + "s</span>" +
        "<span>✍️ Writing: " + msg.meta.writing + "s</span>";
      bubble.appendChild(meta);
    }

    if (msg.widgets && msg.widgets.length) {
      const box = document.createElement("div");
      box.className = "widgets";
      msg.widgets.forEach((w) => {
        const el = buildWidget(w);
        if (el) box.appendChild(el);
      });
      // widgets render above the "Thinking/Writing" footer
      const metaEl = bubble.querySelector(".msg-meta");
      if (metaEl) bubble.insertBefore(box, metaEl);
      else bubble.appendChild(box);
    }

    listEl.appendChild(row);
    scrollToBottom(true);
  }

  /* ---------------------------------------------------------- widgets -- */
  function buildWidget(w) {
    if (w.type === "field") return buildField(w);
    if (w.type === "ticket_button") return buildTicketButton(w);
    if (w.type === "ticket_form") return buildTicketForm(w);
    if (w.type === "map_pin") return buildMapPin(w);
    return null;
  }

  function buildMapPin(w) {
    const wrap = document.createElement("div");
    wrap.className = "map-card";

    const visual = document.createElement("div");
    visual.className = "map-visual";
    visual.innerHTML =
      '<svg class="map-grid" viewBox="0 0 400 160" preserveAspectRatio="none" aria-hidden="true">' +
      '<rect width="400" height="160" fill="#dfe9d8"/>' +
      '<rect x="0" y="28" width="400" height="13" fill="#eef3ea"/>' +
      '<rect x="0" y="98" width="400" height="9" fill="#eef3ea"/>' +
      '<rect x="58" y="0" width="11" height="160" fill="#eef3ea"/>' +
      '<rect x="252" y="0" width="15" height="160" fill="#eef3ea"/>' +
      '<rect x="14" y="52" width="70" height="34" rx="4" fill="#cfe0c5"/>' +
      '<rect x="300" y="18" width="80" height="40" rx="4" fill="#cfe0c5"/>' +
      '<rect x="118" y="108" width="90" height="36" rx="4" fill="#cfe0c5"/>' +
      "</svg>" +
      '<div class="map-pin">' +
      '<svg viewBox="0 0 32 42" aria-hidden="true">' +
      '<path d="M16 0C7.2 0 0 7.2 0 16c0 11 16 26 16 26s16-15 16-26C32 7.2 24.8 0 16 0z" fill="#e6392f"/>' +
      '<circle cx="16" cy="16" r="6.5" fill="#ffffff"/>' +
      "</svg>" +
      "</div>";
    wrap.appendChild(visual);

    const info = document.createElement("div");
    info.className = "map-info";

    const row = document.createElement("div");
    row.className = "map-info-row";
    const icon = document.createElement("span");
    icon.className = "map-pin-icon";
    icon.textContent = "📍";
    const address = document.createElement("span");
    address.className = "map-address";
    address.textContent = w.address || "";
    row.appendChild(icon);
    row.appendChild(address);
    info.appendChild(row);

    const caption = document.createElement("div");
    caption.className = "map-caption";
    caption.textContent = w.caption || "Shared location";
    info.appendChild(caption);

    wrap.appendChild(info);
    return wrap;
  }

  function buildField(w) {
    const wrap = document.createElement("div");
    wrap.className = "w-field";

    const label = document.createElement("div");
    label.className = "w-label";
    label.textContent = w.label || w.name;
    wrap.appendChild(label);

    const pill = document.createElement("div");
    pill.className = "field-pill";

    if (w.prefix) {
      const prefix = document.createElement("span");
      prefix.className = "prefix";
      prefix.textContent = w.prefix;
      pill.appendChild(prefix);
    }

    const input = document.createElement("input");
    input.type = "text";
    input.autocomplete = "off";
    input.placeholder = w.placeholder || "";
    if (w.maxlength) input.maxLength = w.maxlength;
    if (w.inputmode) input.inputMode = w.inputmode;
    pill.appendChild(input);
    wrap.appendChild(pill);

    const submit = () => {
      const value = input.value.trim();
      if (!value || busy) return;
      input.disabled = true;
      pill.classList.add("done");
      send("/api/action", { action: "field", name: w.name, value: value });
    };

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
    });

    // numeric fields submit automatically once they are complete
    if (w.inputmode === "numeric" && w.maxlength) {
      input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "");
      });
    }

    setTimeout(() => input.focus(), 120);
    return wrap;
  }

  function buildTicketButton(w) {
    const wrap = document.createElement("div");
    wrap.className = "w-choices w-ticket-btn";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pill-btn";
    btn.textContent = w.label || "Create Ticket";
    btn.addEventListener("click", () => {
      if (busy) return;
      disableGroup(btn.closest(".widgets") || wrap);
      send("/api/action", { action: "open_ticket" });
    });
    wrap.appendChild(btn);
    return wrap;
  }

  function buildTicketForm(w) {
    const max = w.maxlength || 500;
    const wrap = document.createElement("div");
    wrap.className = "w-ticket";

    const label = document.createElement("div");
    label.className = "w-label";
    label.textContent = w.label || "Your Ticket Message";
    wrap.appendChild(label);

    const box = document.createElement("div");
    box.className = "ticket-box";

    const ta = document.createElement("textarea");
    ta.placeholder = w.placeholder || "";
    ta.maxLength = max;
    box.appendChild(ta);

    const foot = document.createElement("div");
    foot.className = "ticket-foot";

    const counter = document.createElement("span");
    counter.className = "ticket-counter";
    counter.textContent = "0 / " + max + " characters";
    foot.appendChild(counter);

    const hint = document.createElement("span");
    hint.className = "ticket-hint";
    hint.textContent = "Enter to send • Shift + Enter for a new line";
    foot.appendChild(hint);

    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "ticket-send-btn";
    sendBtn.setAttribute("aria-label", "Send");
    sendBtn.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M21.4 11.1 4.6 3.3a.9.9 0 0 0-1.25 1.05L5.2 11.2a.9.9 0 0 0 .72.65l7.6 1.15-7.6 1.15a.9.9 0 0 0-.72.65l-1.85 6.85A.9.9 0 0 0 4.6 22.7l16.8-7.8a2.1 2.1 0 0 0 0-3.8z"' +
      ' fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    foot.appendChild(sendBtn);

    box.appendChild(foot);
    wrap.appendChild(box);

    const submit = () => {
      const value = ta.value.trim();
      if (!value || busy) return;
      ta.disabled = true;
      sendBtn.disabled = true;
      box.classList.add("done");
      hint.textContent = "Submitted";
      send("/api/action", { action: "field", name: "ticket_description", value: value });
    };

    ta.addEventListener("input", () => {
      counter.textContent = ta.value.length + " / " + max + " characters";
      sendBtn.classList.toggle("active", ta.value.trim().length > 0);
    });

    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    });

    sendBtn.addEventListener("click", submit);

    setTimeout(() => ta.focus(), 120);
    return wrap;
  }

  function disableGroup(container) {
    if (!container) return;
    container.querySelectorAll("button").forEach((b) => (b.disabled = true));
  }

  /* --------------------------------------------------------- transport -- */
  // A few seconds of "typing" per bubble reads as real thinking rather than
  // a canned instant reply - the small per-message delay hints from the
  // backend are intentionally not used here.
  const THINK_MS_MIN = 3000;
  const THINK_MS_MAX = 4000;

  async function playMessages(messages) {
    for (const msg of messages) {
      const typing = showTyping();
      await sleep(THINK_MS_MIN + Math.random() * (THINK_MS_MAX - THINK_MS_MIN));
      typing.remove();
      addBotMessage(msg);
      await sleep(150);
    }
  }

  function setBusy(state) {
    busy = state;
    inputEl.disabled = state;
    sendEl.disabled = state;
    if (!state) inputEl.focus();
  }

  async function send(url, payload) {
    setBusy(true);
    try {
      const data = await post(url, payload);
      await playMessages(data.messages || []);
    } catch (err) {
      addBotMessage({
        html: "<p>Sorry, I could not reach the Telkom assistant service just " +
              "now. Please check your connection and try again.</p>",
      });
      console.error(err);
    } finally {
      setBusy(false);
      scrollToBottom(true);
    }
  }

  /* ------------------------------------------------------------ events -- */
  function enterChat(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    appEl.dataset.view = "chat";
    addUserMessage(text);
    send("/api/message", { text: text });
  }

  function submitComposer() {
    const text = inputEl.value.trim();
    if (!text || busy) return;
    inputEl.value = "";
    updateSendState();
    enterChat(text);
  }

  function submitLanding() {
    const text = landingInputEl.value.trim();
    if (!text || busy) return;
    landingInputEl.value = "";
    enterChat(text);
  }

  function updateSendState() {
    sendEl.classList.toggle("active", inputEl.value.trim().length > 0);
  }

  inputEl.addEventListener("input", updateSendState);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submitComposer(); }
  });
  sendEl.addEventListener("click", submitComposer);

  landingInputEl.addEventListener("input", () => {
    landingSendEl.classList.toggle("active", landingInputEl.value.trim().length > 0);
  });
  landingInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submitLanding(); }
  });
  landingSendEl.addEventListener("click", submitLanding);

  suggestionCards.forEach((card) => {
    card.addEventListener("click", () => enterChat(card.dataset.question));
  });

  homeEl.addEventListener("click", async () => {
    if (busy) return;
    listEl.innerHTML = "";
    sessionStorage.removeItem("tk_session_id");
    try {
      await post("/api/reset", {});
    } catch (err) {
      console.error(err);
    }
    appEl.dataset.view = "landing";
    landingInputEl.value = "";
    landingSendEl.classList.remove("active");
  });

  /* -------------------------------------------------------------- boot -- */
  // The landing hero screen doubles as the greeting - the chat transcript
  // only appears once the user sends their first message or taps a
  // suggestion card. Reset silently so a page reload mid-conversation
  // (e.g. stuck waiting for an OTP) can't leave the backend session
  // stuck on an old step once the user starts fresh from this screen.
  post("/api/reset", {}).catch((err) => console.error(err));
  landingInputEl.focus();
})();
