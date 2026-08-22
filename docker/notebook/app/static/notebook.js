(() => {
  "use strict";

  const state = {
    chapters: window.NOTEBOOK_DATA.chapters,
    progress: window.NOTEBOOK_DATA.progress,
    activeChapterId: null,
    renderedDialogueKeys: new Set(),
  };

  const elements = {
    tabs: document.querySelector("#chapter-tabs"),
    title: document.querySelector("#chapter-title"),
    eyebrow: document.querySelector("#chapter-eyebrow"),
    date: document.querySelector("#chapter-date"),
    status: document.querySelector("#chapter-status"),
    objective: document.querySelector("#chapter-objective"),
    lead: document.querySelector("#chapter-lead"),
    blocks: document.querySelector("#chapter-blocks"),
    progressCount: document.querySelector("#progress-count"),
    progressFill: document.querySelector("#progress-fill"),
    pageNumber: document.querySelector("#page-number"),
    toast: document.querySelector("#toast"),
  };

  function chapterById(chapterId) {
    return state.chapters.find((chapter) => chapter.id === chapterId);
  }

  function isUnlocked(chapterId) {
    return state.progress.unlocked_chapter_ids.includes(chapterId);
  }

  function isComplete(chapterId) {
    return state.progress.completed_chapter_ids.includes(chapterId);
  }

  function firstCurrentChapter() {
    const availableUnlocked = state.chapters.filter(
      (chapter) => chapter.available && isUnlocked(chapter.id),
    );
    return availableUnlocked.find((chapter) => !isComplete(chapter.id)) || availableUnlocked.at(-1);
  }

  function setText(element, value) {
    element.textContent = value || "";
  }

  function renderNavigation() {
    elements.tabs.replaceChildren();
    state.chapters.forEach((chapter) => {
      const unlocked = isUnlocked(chapter.id);
      const complete = isComplete(chapter.id);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chapter-tab";
      button.dataset.chapterId = chapter.id;
      button.disabled = !unlocked;
      button.setAttribute("aria-current", chapter.id === state.activeChapterId ? "page" : "false");
      button.innerHTML = `
        <span class="tab-number">${escapeHtml(chapter.number)}</span>
        <span class="tab-label">${escapeHtml(chapter.nav_title)}</span>
        <span class="tab-state" aria-hidden="true">${complete ? "済" : unlocked ? "開" : "封"}</span>
      `;
      if (complete) button.classList.add("is-complete");
      if (!unlocked) button.classList.add("is-locked");
      button.addEventListener("click", () => switchChapter(chapter.id));
      elements.tabs.append(button);
    });
  }

  function createSectionHeading(block, headingId) {
    const heading = document.createElement("div");
    heading.className = `section-heading${block.heading.number ? "" : " is-unnumbered"}`;
    if (block.heading.number) {
      const number = document.createElement("span");
      number.className = "section-number";
      number.textContent = block.heading.number;
      heading.append(number);
    }

    const copy = document.createElement("div");
    const kicker = document.createElement("p");
    kicker.textContent = block.heading.kicker;
    const title = document.createElement("h2");
    title.id = headingId;
    title.textContent = block.heading.title;
    copy.append(kicker, title);
    heading.append(copy);
    return heading;
  }

  function createDialogue(entry, animate) {
    const row = document.createElement("article");
    row.className = `dialogue-row ${entry.speaker === "player" ? "is-player" : "is-director"}`;
    if (animate) row.classList.add("is-new");

    const speakerName = entry.speaker === "player" ? "あなた" : "所長";
    const avatarFile = entry.speaker === "player" ? "avatar-player.png" : "avatar-director.png";
    row.innerHTML = `
      <div class="avatar-wrap" aria-hidden="true">
        <img src="/static/images/${avatarFile}" alt="">
      </div>
      <div class="dialogue-body">
        <span class="speaker-name">${speakerName}</span>
        <p>${escapeHtml(entry.text)}</p>
      </div>
    `;
    return row;
  }

  function appendDialogueMessages(container, block, context) {
    block.messages.forEach((message, index) => {
      const keyParts = [context.chapter.id];
      if (context.question) keyParts.push(context.question.id);
      keyParts.push(block.id, String(index));
      const key = keyParts.join(":");
      const animate = context.animateNew && !context.previousKeys.has(key);
      const row = createDialogue(message, animate);
      container.append(row);
      state.renderedDialogueKeys.add(key);
      if (animate) context.newRows.push(row);
    });
  }

  function renderDialogueBlock(block, context) {
    if (context.question) {
      const followUp = document.createElement("div");
      followUp.className = "question-dialogue";
      followUp.setAttribute("aria-label", block.heading.title);
      const heading = document.createElement("p");
      heading.className = "question-dialogue-heading";
      const kicker = document.createElement("span");
      kicker.textContent = block.heading.kicker;
      heading.append(kicker, document.createTextNode(block.heading.title));
      followUp.append(heading);
      appendDialogueMessages(followUp, block, context);
      return followUp;
    }

    const section = document.createElement("section");
    section.className = "conversation-section dialogue-section";
    const headingId = `heading-${context.chapter.id}-${block.id}`;
    section.setAttribute("aria-labelledby", headingId);
    section.append(createSectionHeading(block, headingId));
    const log = document.createElement("div");
    log.className = "conversation-log";
    log.setAttribute("aria-live", "polite");
    appendDialogueMessages(log, block, context);
    section.append(log);
    return section;
  }

  function renderDocumentBlock(block, context) {
    const section = document.createElement("section");
    section.className = "source-document";
    const headingId = `heading-${context.chapter.id}-${block.id}`;
    section.setAttribute("aria-labelledby", headingId);
    section.append(createSectionHeading(block, headingId));

    const documentData = block.content;
    const article = document.createElement("article");
    article.className = "request-letter";
    article.setAttribute("aria-label", block.heading.title);
    article.innerHTML = `
      <div class="letter-tape" aria-hidden="true"></div>
      <p class="document-kicker">${escapeHtml(documentData.kicker)}</p>
      <h3>${escapeHtml(documentData.title)}</h3>
    `;
    const receivedStamp = document.createElement("div");
    receivedStamp.className = "letter-received";
    receivedStamp.setAttribute("aria-hidden", "true");
    receivedStamp.textContent = documentData.received_stamp;
    article.prepend(receivedStamp);

    const body = document.createElement("div");
    body.className = "document-body";
    documentData.body.forEach((paragraph, index) => {
      const paragraphElement = document.createElement("p");
      paragraphElement.textContent = paragraph;
      if (index === 0 || index === documentData.body.length - 1) {
        paragraphElement.classList.add("letter-emphasis");
      }
      body.append(paragraphElement);
    });

    const footer = document.createElement("footer");
    footer.className = "document-signoff";
    const date = document.createElement("time");
    date.textContent = documentData.date;
    const signature = document.createElement("strong");
    signature.textContent = documentData.signature;
    footer.append(date, signature);
    article.append(body, footer);
    section.append(article);
    return section;
  }

  function renderEvidenceNoteBlock(block, context) {
    const section = document.createElement("section");
    section.className = "evidence-section";
    section.dataset.component = "evidence-note";
    section.dataset.blockId = block.id;
    const headingId = `heading-${context.chapter.id}-${block.id}`;
    section.setAttribute("aria-labelledby", headingId);
    section.append(createSectionHeading(block, headingId));

    const card = document.createElement("div");
    card.className = "evidence-card";
    const inputId = `note-${context.chapter.id}-${block.id}`;
    const label = document.createElement("label");
    label.htmlFor = inputId;
    label.textContent = block.label;
    const textarea = document.createElement("textarea");
    textarea.id = inputId;
    textarea.rows = 5;
    textarea.maxLength = 4000;
    textarea.placeholder = block.placeholder;
    textarea.value = state.progress.notes[context.chapter.id]?.content || "";

    const actions = document.createElement("div");
    actions.className = "evidence-actions";
    const status = document.createElement("span");
    status.className = "save-status";
    status.dataset.role = "note-status";
    status.setAttribute("role", "status");
    status.textContent = state.progress.notes[context.chapter.id] ? "保存済み" : "未保存";
    const button = document.createElement("button");
    button.className = "ink-button secondary";
    button.type = "button";
    button.textContent = block.action_label;
    button.addEventListener("click", submitNote);
    textarea.addEventListener("input", () => setText(status, "編集中…"));
    actions.append(status, button);
    card.append(label, textarea, actions);
    section.append(card);
    return section;
  }

  function renderHintsBlock(block) {
    const hints = document.createElement("div");
    hints.className = "hints";
    block.items.forEach((hint, index) => {
      const details = document.createElement("details");
      details.className = "hint-note";
      details.innerHTML = `
        <summary>所長の付箋 ${index + 1}</summary>
        <p>${formatInlineCode(hint)}</p>
      `;
      hints.append(details);
    });
    return hints;
  }

  function renderQuestionBlock(question, context, index) {
    const solved = state.progress.solved_question_ids.includes(question.id);
    const savedAnswer = state.progress.answers[question.id]?.answer || "";
    const form = document.createElement("form");
    form.className = `question-card${solved ? " is-solved" : ""}`;
    form.dataset.questionId = question.id;
    form.style.setProperty("--question-index", index);
    form.innerHTML = `
      <div class="question-topline">
        <span>${escapeHtml(question.label)}</span>
        <span class="question-result">${solved ? "記録済み" : "未解決"}</span>
      </div>
      <label for="answer-${question.id}">${escapeHtml(question.prompt)}</label>
      <div class="answer-row">
        <span class="pencil-mark" aria-hidden="true">✎</span>
        <input
          id="answer-${question.id}"
          name="answer"
          type="text"
          value="${escapeAttribute(savedAnswer)}"
          placeholder="${escapeAttribute(question.placeholder)}"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          ${question.input_mode === "numeric" ? 'inputmode="numeric"' : ""}
          ${solved ? "disabled" : ""}
        >
        <button class="ink-button" type="submit" ${solved ? "disabled" : ""}>
          ${solved ? "記録済み" : "照合する"}
        </button>
      </div>
      <p class="answer-feedback" role="status">${solved ? "証拠との一致を確認しました。" : ""}</p>
    `;

    renderBlocks(question.blocks, {
      ...context,
      container: form,
      question,
    });
    form.addEventListener("submit", submitAnswer);
    return form;
  }

  function renderQuestionsBlock(block, context) {
    const section = document.createElement("section");
    section.className = "questions-section";
    const headingId = `heading-${context.chapter.id}-${block.id}`;
    section.setAttribute("aria-labelledby", headingId);
    section.append(createSectionHeading(block, headingId));
    const list = document.createElement("div");
    list.className = "questions-list";
    section.append(list);
    renderBlocks(block.items, { ...context, container: list });
    return section;
  }

  const blockRenderers = {
    dialogue: renderDialogueBlock,
    document: renderDocumentBlock,
    evidence_note: renderEvidenceNoteBlock,
    hints: renderHintsBlock,
    question: renderQuestionBlock,
    questions: renderQuestionsBlock,
  };

  function renderBlocks(blocks, context) {
    blocks.forEach((block, index) => {
      const renderer = blockRenderers[block.type];
      if (!renderer) return;
      const rendered = renderer(block, context, index);
      if (rendered) context.container.append(rendered);
    });
  }

  function renderProgress() {
    const solved = state.progress.solved_count;
    const total = state.progress.total_questions;
    const percent = total ? Math.round((solved / total) * 100) : 0;
    setText(elements.progressCount, `${solved} / ${total}`);
    elements.progressFill.style.width = `${percent}%`;
  }

  function renderChapter({ animateNewDialogue = false } = {}) {
    const chapter = chapterById(state.activeChapterId);
    const chapterIndex = state.chapters.findIndex((item) => item.id === chapter.id);
    const renderContext = {
      animateNew: animateNewDialogue,
      chapter,
      container: elements.blocks,
      previousKeys: new Set(state.renderedDialogueKeys),
      newRows: [],
    };

    setText(elements.eyebrow, chapter.eyebrow);
    setText(elements.title, chapter.title);
    setText(elements.date, chapter.date);
    setText(elements.status, isComplete(chapter.id) ? "調査済" : chapter.status_label);
    setText(elements.objective, chapter.objective);
    setText(elements.lead, chapter.lead);
    setText(elements.pageNumber, `— ${String(chapterIndex + 1).padStart(2, "0")} —`);
    elements.blocks.replaceChildren();
    renderBlocks(chapter.blocks, renderContext);
    renderNavigation();
    renderProgress();

    if (animateNewDialogue) {
      renderContext.newRows.at(-1)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function switchChapter(chapterId) {
    if (!isUnlocked(chapterId)) return;
    state.activeChapterId = chapterId;
    state.renderedDialogueKeys.clear();
    renderChapter();
    document.querySelector("#notebook-page").scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submitAnswer(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.answer;
    const button = form.querySelector("button[type='submit']");
    const feedback = form.querySelector(".answer-feedback");
    button.disabled = true;
    button.textContent = "照合中…";
    feedback.textContent = "";

    try {
      const response = await fetch(`/api/answers/${form.dataset.questionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer: input.value }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "照合できませんでした。");

      feedback.textContent = result.message;
      feedback.classList.toggle("is-error", !result.correct);
      if (!result.correct) {
        form.classList.add("has-error");
        window.setTimeout(() => form.classList.remove("has-error"), 420);
        return;
      }

      state.progress = result.progress;
      state.chapters = result.chapters;
      renderChapter({ animateNewDialogue: result.newly_solved });
      showToast("正解。新しい会話が追加されました。");
    } catch (error) {
      feedback.textContent = error.message;
      feedback.classList.add("is-error");
    } finally {
      const currentForm = document.querySelector(`[data-question-id="${form.dataset.questionId}"]`);
      const currentButton = currentForm?.querySelector("button[type='submit']");
      if (currentButton && !currentForm.classList.contains("is-solved")) {
        currentButton.disabled = false;
        currentButton.textContent = "照合する";
      }
    }
  }

  async function submitNote(event) {
    const section = event.currentTarget.closest('[data-component="evidence-note"]');
    const textarea = section.querySelector("textarea");
    const status = section.querySelector('[data-role="note-status"]');
    const button = event.currentTarget;
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = "保存中…";

    try {
      const response = await fetch(`/api/notes/${state.activeChapterId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: textarea.value }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "保存できませんでした。");
      if (!result.saved) {
        setText(status, result.message);
        return;
      }
      state.progress = result.progress;
      state.chapters = result.chapters;
      renderChapter({ animateNewDialogue: result.first_note });
      showToast(result.first_note ? "証拠を保存。会話が追加されました。" : "証拠メモを更新しました。");
    } catch (error) {
      setText(status, error.message);
    } finally {
      if (document.contains(button)) {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    }
  }

  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    window.clearTimeout(showToast.timeoutId);
    showToast.timeoutId = window.setTimeout(() => {
      elements.toast.classList.remove("is-visible");
    }, 2800);
  }

  function escapeHtml(value) {
    const element = document.createElement("span");
    element.textContent = value;
    return element.innerHTML;
  }

  function escapeAttribute(value) {
    return String(value).replace(/[&<>"'`]/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
      "`": "&#96;",
    })[character]);
  }

  function formatInlineCode(value) {
    return escapeHtml(value).replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  state.activeChapterId = firstCurrentChapter().id;
  renderChapter();
})();
