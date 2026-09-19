(() => {
  "use strict";

  const notebookOrigin = `${window.location.protocol}//${window.location.hostname}:8080`;
  let dirty = false;

  const toggle = document.createElement("button");
  toggle.id = "sushictf-note-toggle";
  toggle.type = "button";
  toggle.setAttribute("aria-controls", "sushictf-note-panel");
  toggle.setAttribute("aria-expanded", "false");
  toggle.textContent = "調査メモ";

  const panel = document.createElement("aside");
  panel.id = "sushictf-note-panel";
  panel.setAttribute("aria-label", "調査メモ");
  panel.setAttribute("aria-hidden", "true");
  panel.innerHTML = `
    <div class="sushictf-note-header">
      <div>
        <span>EVIDENCE MEMO</span>
        <strong>見つけた証拠</strong>
      </div>
      <button type="button" class="sushictf-note-close" aria-label="調査メモを閉じる">×</button>
    </div>
    <label for="sushictf-note-content">調査中に確認した事実や、気になった言葉を自由に書き留める</label>
    <textarea id="sushictf-note-content" maxlength="12000" placeholder="例：見つけたページ、人物名、数字、気になった表現……"></textarea>
    <div class="sushictf-note-actions">
      <span class="sushictf-note-status" role="status">入力すると自動同期します</span>
    </div>
  `;

  document.body.append(toggle, panel);

  const closeButton = panel.querySelector(".sushictf-note-close");
  const textarea = panel.querySelector("textarea");
  const status = panel.querySelector(".sushictf-note-status");
  let saveTimer;

  function setOpen(open) {
    panel.classList.toggle("is-open", open);
    panel.setAttribute("aria-hidden", String(!open));
    toggle.setAttribute("aria-expanded", String(open));
    if (open) {
      loadNote();
      textarea.focus();
    }
  }

  async function loadNote() {
    if (dirty) return;
    status.textContent = "読込中…";
    try {
      const response = await fetch(`${notebookOrigin}/api/note`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "調査メモを読み込めませんでした。");
      textarea.value = result.content || "";
      status.textContent = result.updated_at ? "同期済み" : "入力すると自動同期します";
    } catch (error) {
      status.textContent = error.message;
    }
  }

  function scheduleSave(delay = 500) {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveNote, delay);
  }

  async function saveNote() {
    const content = textarea.value;
    status.textContent = "同期中…";
    try {
      const response = await fetch(`${notebookOrigin}/api/note`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "調査メモを保存できませんでした。");
      if (textarea.value === content) {
        dirty = false;
        status.textContent = "同期済み";
      }
    } catch (error) {
      status.textContent = "同期できません。再試行中…";
      scheduleSave(2000);
    }
  }

  toggle.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
  closeButton.addEventListener("click", () => setOpen(false));
  textarea.addEventListener("input", () => {
    dirty = true;
    status.textContent = "編集中…";
    scheduleSave();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.classList.contains("is-open")) setOpen(false);
  });

  const noteEvents = new EventSource(`${notebookOrigin}/api/note/events`);
  noteEvents.addEventListener("message", (event) => {
    if (dirty) return;
    try {
      const note = JSON.parse(event.data);
      textarea.value = note.content || "";
      status.textContent = note.updated_at ? "同期済み" : "入力すると自動同期します";
    } catch (_error) {
      // EventSourceが再接続すると最新値が再送される。
    }
  });
})();
