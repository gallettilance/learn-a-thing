async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Save failed");
  return data;
}

function showFormMsg(form, text, isError = false) {
  const msg = form.querySelector(".form-msg");
  if (!msg) return;
  msg.hidden = false;
  msg.classList.toggle("error", isError);
  msg.textContent = text;
}

document.querySelectorAll(".engagement-form").forEach((form) => {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const section = form.closest(".engagement-inline");
    if (!section) return;

    const date = section.dataset.date;
    const lesson = section.dataset.lesson;
    const fd = new FormData(form);
    const payload = {
      date,
      lesson,
      status: fd.get("status") || "unread",
      depth: fd.get("depth") || null,
      interest: fd.get("interest") || null,
      note: fd.get("note") || null,
    };

    try {
      await postJson("/api/engagement", payload);
      showFormMsg(form, "Saved — curator will use this tomorrow.");
    } catch (err) {
      showFormMsg(
        form,
        "Could not save (is the local server running?). Copy to engagement.yaml manually.",
        true
      );
    }
  });
});

document.querySelectorAll(".hyp-confidence-form").forEach((form) => {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const section = form.closest(".hypothesis-confidence-inline");
    if (!section) return;

    const id = section.dataset.id;
    const fd = new FormData(form);
    const learner_confidence = fd.get("learner_confidence");
    if (!learner_confidence) {
      showFormMsg(form, "Pick a confidence level first.", true);
      return;
    }

    try {
      await postJson("/api/hypothesis-confidence", { id, learner_confidence });
      showFormMsg(form, "Saved — curator will prioritize fuzzy models.");
    } catch (err) {
      showFormMsg(
        form,
        "Could not save (is the local server running?). Copy to hypothesis-confidence.yaml manually.",
        true
      );
    }
  });
});

function bindTopicMastery(root = document) {
  root.querySelectorAll(".topic-mastery-inline:not([data-bound])").forEach((section) => {
    section.dataset.bound = "1";
    const checkbox = section.querySelector('input[name="mastered"]');
    if (!checkbox) return;

    checkbox.addEventListener("change", async () => {
      const topic = section.dataset.topic;
      const mastered = checkbox.checked;
      const msg = section.querySelector(".form-msg");
      try {
        await postJson("/api/topic-mastery", { topic_label: topic, mastered });
        if (msg) {
          msg.hidden = false;
          msg.classList.remove("error");
          msg.textContent = mastered
            ? "Marked mastered — curator will skip intro on this topic."
            : "Unmarked — topic back in rotation.";
        }
        section.classList.toggle("is-mastered", mastered);
      } catch (err) {
        checkbox.checked = !mastered;
        if (msg) {
          msg.hidden = false;
          msg.classList.add("error");
          msg.textContent =
            "Could not save (is the local server running?). Edit learner/mastered-topics.yaml manually.";
        }
      }
    });
  });
}

bindTopicMastery();
window.bindTopicMastery = bindTopicMastery;

function bindConceptMastery(root = document) {
  root.querySelectorAll(".concept-mastery-inline:not([data-bound])").forEach((section) => {
    section.dataset.bound = "1";
    const checkbox = section.querySelector('input[name="concept_mastered"]');
    if (!checkbox) return;

    checkbox.addEventListener("change", async () => {
      const conceptId = section.dataset.concept;
      const mastered = checkbox.checked;
      const msg = section.querySelector(".form-msg");
      try {
        await postJson("/api/concept-mastery", {
          concept_id: conceptId,
          mastered,
          topic_label: section.dataset.topic || "",
          lesson_ref: section.dataset.lessonRef || "",
        });
        if (msg) {
          msg.hidden = false;
          msg.classList.remove("error");
          msg.textContent = mastered
            ? "Concept marked — prerequisite gate will allow dependent lessons."
            : "Concept unmarked — dependent lessons may defer again.";
        }
        section.classList.toggle("is-mastered", mastered);
      } catch (err) {
        checkbox.checked = !mastered;
        if (msg) {
          msg.hidden = false;
          msg.classList.add("error");
          msg.textContent =
            "Could not save (is the local server running?). Edit learner/concept-mastery.yaml manually.";
        }
      }
    });
  });
}

bindConceptMastery();
window.bindConceptMastery = bindConceptMastery;
