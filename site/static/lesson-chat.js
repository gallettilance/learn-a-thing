/** Per-lesson follow-up chat — loads/saves via /api/lesson-chat */

function escChat(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderChatMessage(msg) {
  const role = msg.role === "assistant" ? "assistant" : "user";
  return `<div class="lesson-chat-msg lesson-chat-msg-${role}"><div class="lesson-chat-bubble">${escChat(msg.content)}</div></div>`;
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function initLessonChat(section) {
  const date = section.dataset.date;
  const lesson = section.dataset.lesson;
  const topic = section.dataset.topic || "";
  const log = section.querySelector(".lesson-chat-log");
  const form = section.querySelector(".lesson-chat-form");
  if (!log || !form) return;

  const loadThread = async () => {
    try {
      const data = await fetchJson(
        `/api/lesson-chat?date=${encodeURIComponent(date)}&lesson=${encodeURIComponent(lesson)}`
      );
      const messages = data.messages || [];
      log.innerHTML = messages.length
        ? messages.map(renderChatMessage).join("")
        : '<p class="hint lesson-chat-empty">No messages yet — ask anything that felt fuzzy.</p>';
      log.scrollTop = log.scrollHeight;
    } catch {
      log.innerHTML = '<p class="hint lesson-chat-empty">Start the local server to load chat history.</p>';
    }
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const textarea = form.querySelector('textarea[name="message"]');
    const msgEl = form.querySelector(".form-msg");
    const button = form.querySelector('button[type="submit"]');
    const message = (textarea?.value || "").trim();
    if (!message) return;

    if (button) button.disabled = true;
    if (msgEl) msgEl.hidden = true;

    const empty = log.querySelector(".lesson-chat-empty");
    if (empty) empty.remove();
    log.insertAdjacentHTML("beforeend", renderChatMessage({ role: "user", content: message }));
    log.insertAdjacentHTML(
      "beforeend",
      '<div class="lesson-chat-msg lesson-chat-msg-assistant lesson-chat-pending"><div class="lesson-chat-bubble">…</div></div>'
    );
    log.scrollTop = log.scrollHeight;
    if (textarea) textarea.value = "";

    try {
      const data = await fetchJson("/api/lesson-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date, lesson, message, topic_label: topic }),
      });
      const pending = log.querySelector(".lesson-chat-pending");
      if (pending) pending.remove();
      if (data.assistant) {
        log.insertAdjacentHTML("beforeend", renderChatMessage({ role: "assistant", content: data.assistant }));
      } else if (data.saved_only) {
        log.insertAdjacentHTML(
          "beforeend",
          renderChatMessage({
            role: "assistant",
            content:
              "Saved for the editor — your question will shape traps and checkpoints in future lessons. Set CURSOR_API_KEY when running serve.py for live tutor replies.",
          })
        );
      }
      if (msgEl) {
        msgEl.hidden = false;
        msgEl.classList.remove("error");
        msgEl.textContent = "Saved — editor will anticipate this kind of question.";
      }
    } catch (err) {
      const pending = log.querySelector(".lesson-chat-pending");
      if (pending) pending.remove();
      if (msgEl) {
        msgEl.hidden = false;
        msgEl.classList.add("error");
        msgEl.textContent =
          "Could not save (is python site/serve.py running?). Copy to learner/lesson-chat.yaml manually.";
      }
    } finally {
      if (button) button.disabled = false;
      log.scrollTop = log.scrollHeight;
    }
  });

  loadThread();
}

document.querySelectorAll(".lesson-chat").forEach(initLessonChat);
