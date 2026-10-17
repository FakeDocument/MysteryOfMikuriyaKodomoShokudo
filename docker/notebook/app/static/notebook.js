(() => {
  "use strict";

  const state = {
    chapters: window.NOTEBOOK_DATA.chapters,
    progress: window.NOTEBOOK_DATA.progress,
    activeChapterId: null,
    renderedDialogueKeys: new Set(),
  };

  const dialogueSpeakers = window.NOTEBOOK_DATA.dialogue_speakers;

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

  function setMarkdown(element, value) {
    element.innerHTML = window.NotebookMarkdown.render(value);
  }

  function setInlineMarkdown(element, value) {
    element.innerHTML = window.NotebookMarkdown.renderInline(value || "");
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
    if (entry.speaker === "narrator") {
      row.className = "dialogue-row is-narrator";
      if (animate) row.classList.add("is-new");
      const copy = document.createElement("div");
      copy.className = "narration-copy";
      setMarkdown(copy, entry.text);
      row.append(copy);
      return row;
    }

    const speaker = dialogueSpeakers[entry.speaker];
    const expression = entry.expression || speaker.defaultExpression;
    const avatarFile = speaker.avatars[expression];
    row.className = `dialogue-row is-${entry.speaker}`;
    row.dataset.expression = expression;
    if (animate) row.classList.add("is-new");

    row.innerHTML = `
      <div class="avatar-wrap" aria-hidden="true">
        <img src="/static/images/${avatarFile}" alt="" width="128" height="128">
      </div>
      <div class="dialogue-body">
        <span class="speaker-name">${speaker.name}</span>
        <div class="dialogue-copy"></div>
      </div>
    `;
    const copy = row.querySelector(".dialogue-copy");
    setMarkdown(copy, entry.text);
    if (entry.link) {
      const link = document.createElement("a");
      link.className = "dialogue-link";
      link.href = entry.link.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = entry.link.label;
      copy.append(link);
    }
    if (entry.image) {
      const figure = document.createElement("figure");
      figure.className = "dialogue-image";

      const imageLink = document.createElement("a");
      imageLink.className = "dialogue-image-link";
      imageLink.href = entry.image.src;
      imageLink.target = "_blank";
      imageLink.rel = "noopener noreferrer";
      imageLink.setAttribute("aria-label", `${entry.image.alt}（原寸で開く）`);

      const image = document.createElement("img");
      image.src = entry.image.src;
      image.alt = entry.image.alt;
      image.loading = "lazy";
      image.decoding = "async";
      imageLink.append(image);
      figure.append(imageLink);

      if (entry.image.caption) {
        const caption = document.createElement("figcaption");
        caption.textContent = entry.image.caption;
        figure.append(caption);
      }
      row.querySelector(".dialogue-body").append(figure);
    }
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
      const paragraphElement = document.createElement("div");
      paragraphElement.className = "document-paragraph";
      setMarkdown(paragraphElement, paragraph);
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
    textarea.maxLength = 12000;
    textarea.placeholder = block.placeholder;
    textarea.value = state.progress.note?.content || "";
    textarea.dataset.dirty = "false";

    const actions = document.createElement("div");
    actions.className = "evidence-actions";
    const status = document.createElement("span");
    status.className = "save-status";
    status.dataset.role = "note-status";
    status.setAttribute("role", "status");
    status.textContent = state.progress.note?.updated_at ? "同期済み" : "入力すると自動同期します";
    textarea.addEventListener("input", () => {
      textarea.dataset.dirty = "true";
      setText(status, "編集中…");
      scheduleNoteSave(textarea, status);
    });
    actions.append(status);
    card.append(label, textarea, actions);
    section.append(card);
    return section;
  }

  function renderReportBlock(block, context) {
    const section = document.createElement("section");
    section.className = "report-section";
    const headingId = `heading-${context.chapter.id}-${block.id}`;
    section.setAttribute("aria-labelledby", headingId);
    section.append(createSectionHeading(block, headingId));

    const report = document.createElement("article");
    report.className = "case-report";
    const subject = document.createElement("h3");
    subject.textContent = block.subject;
    const facts = document.createElement("dl");
    block.items.forEach((item) => {
      const label = document.createElement("dt");
      label.textContent = item.label;
      const value = document.createElement("dd");
      value.textContent = item.value;
      facts.append(label, value);
    });
    const conclusion = document.createElement("p");
    conclusion.className = "report-conclusion";
    setInlineMarkdown(conclusion, block.conclusion);
    report.append(subject, facts, conclusion);
    section.append(report);
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
        <div class="hint-copy">${window.NotebookMarkdown.render(hint)}</div>
      `;
      hints.append(details);
    });
    return hints;
  }

  function savedAnswerParts(savedAnswer, fieldCount) {
    if (!savedAnswer) return Array(fieldCount).fill("");
    const tabParts = savedAnswer.split("\t");
    if (tabParts.length === fieldCount) return tabParts;

    const tokens = savedAnswer.trim().split(/\s+/);
    if (fieldCount === 2 && tokens.length >= 2) {
      return [tokens[0].replace(/\/tcp$/i, ""), tokens.at(-1)];
    }
    return [...tokens.slice(0, fieldCount - 1), tokens.slice(fieldCount - 1).join(" ")];
  }

  function dateTimeInputValue(value, chapterDate) {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return value;
    const match = value.match(/^(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:午前|深夜)(\d{1,2})時$/);
    if (!match) return "";
    const year = match[1] || chapterDate.match(/^\d{4}/)?.[0];
    if (!year) return "";
    const pad = (part) => part.padStart(2, "0");
    return `${year}-${pad(match[2])}-${pad(match[3])}T${pad(match[4])}:00`;
  }

  function createAnswerInputs(question, savedAnswer, solved, chapterDate) {
    if (!question.answer_fields) {
      return `
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
      `;
    }

    const values = savedAnswerParts(savedAnswer, question.answer_fields.length);
    const hasDateTime = question.answer_fields.some((field) => field.input_mode === "datetime");
    const fields = question.answer_fields.map((field, index) => {
      const isDateTime = field.input_mode === "datetime";
      const value = isDateTime
        ? dateTimeInputValue(values[index] || "", chapterDate) || "2026-09-11T00:00"
        : values[index] || "";
      if (field.input_mode === "select") {
        // Preserve answers saved before a text field was converted to a select.
        const options = value && !field.options.includes(value) ? [value, ...field.options] : field.options;
        return `
          <label class="answer-field" for="answer-${question.id}-${field.id}">
            <span class="answer-field-label">${escapeHtml(field.label)}</span>
            <select id="answer-${question.id}-${field.id}" name="answer_${field.id}" data-answer-part required ${solved ? "disabled" : ""}>
              <option value="">${escapeHtml(field.placeholder)}</option>
              ${options.map((option) => `<option value="${escapeAttribute(option)}" ${option === value ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
            </select>
          </label>`;
      }
      return `
      <label class="answer-field" for="answer-${question.id}-${field.id}">
        <span class="answer-field-label">${escapeHtml(field.label)}</span>
        <input
          id="answer-${question.id}-${field.id}"
          name="answer_${field.id}"
          data-answer-part
          type="${isDateTime ? "datetime-local" : "text"}"
          value="${escapeAttribute(value)}"
          placeholder="${escapeAttribute(field.placeholder)}"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          ${field.input_mode === "numeric" ? 'inputmode="numeric"' : ""}
          ${isDateTime ? 'step="60"' : ""}
          ${solved ? "disabled" : ""}
        >
      </label>
    `;
    }).join("");
    return `<div class="answer-fields${hasDateTime ? " has-datetime" : ""}" aria-label="回答欄">${fields}</div>`;
  }

  function renderQuestionBlock(question, context, index) {
    const solved = state.progress.solved_question_ids.includes(question.id);
    const savedAnswer = state.progress.answers[question.id]?.answer || "";
    const form = document.createElement("form");
    form.className = `question-card${solved ? " is-solved" : ""}`;
    form.dataset.questionId = question.id;
    form.style.setProperty("--question-index", index);
    const promptId = `question-prompt-${question.id}`;
    const prompt = question.answer_fields
      ? `<p class="question-prompt" id="${promptId}">${window.NotebookMarkdown.renderInline(question.prompt)}</p>`
      : `<label for="answer-${question.id}">${window.NotebookMarkdown.renderInline(question.prompt)}</label>`;
    form.innerHTML = `
      <div class="question-topline">
        <span>${escapeHtml(question.label)}</span>
        <span class="question-result">${solved ? "記録済み" : "未解決"}</span>
      </div>
      ${prompt}
      <div class="answer-row">
        <span class="pencil-mark" aria-hidden="true">✎</span>
        ${createAnswerInputs(question, savedAnswer, solved, context.chapter.date)}
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
    report: renderReportBlock,
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
    setText(elements.status, isComplete(chapter.id) ? (chapter.id === "finale" ? "報告完了" : "調査済") : chapter.status_label);
    setInlineMarkdown(elements.objective, chapter.objective);
    setInlineMarkdown(elements.lead, chapter.lead);
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
    const answerParts = [...form.querySelectorAll("[data-answer-part]")];
    const answer = answerParts.length
      ? answerParts.map((input) => input.value.trim()).join("\t")
      : form.elements.answer.value;
    const button = form.querySelector("button[type='submit']");
    const feedback = form.querySelector(".answer-feedback");

    if (answerParts.some((input) => !input.value.trim())) {
      const missingLabels = answerParts
        .filter((input) => !input.value.trim())
        .map((input) => input.closest(".answer-field")?.querySelector(".answer-field-label")?.textContent)
        .filter(Boolean);
      feedback.textContent = `${missingLabels.join("と")}を入力してください。`;
      feedback.classList.add("is-error");
      return;
    }

    button.disabled = true;
    button.textContent = "照合中…";
    feedback.textContent = "";

    try {
      const response = await fetch(`/api/answers/${form.dataset.questionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
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

  function scheduleNoteSave(textarea, status, delay = 500) {
    window.clearTimeout(scheduleNoteSave.timeoutId);
    scheduleNoteSave.timeoutId = window.setTimeout(
      () => saveSharedNote(textarea, status),
      delay,
    );
  }

  async function saveSharedNote(textarea, status) {
    const content = textarea.value;
    setText(status, "同期中…");

    try {
      const response = await fetch("/api/note", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "保存できませんでした。");
      state.progress.note = result.note;
      if (textarea.value === content) {
        textarea.dataset.dirty = "false";
        setText(status, "同期済み");
      }
    } catch (error) {
      if (document.contains(textarea) && textarea.dataset.dirty === "true") {
        setText(status, "同期できません。再試行中…");
        scheduleNoteSave(textarea, status, 2000);
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

  async function refreshSharedNote() {
    const textarea = document.querySelector('[data-component="evidence-note"] textarea');
    if (!textarea || textarea.dataset.dirty === "true") return;
    try {
      const response = await fetch("/api/note");
      if (!response.ok) return;
      const note = await response.json();
      if ((state.progress.note?.updated_at || null) === (note.updated_at || null)) return;
      applySharedNote(note);
    } catch (_error) {
      // 一時的に取得できなくても、表示中のメモと編集内容は維持する。
    }
  }

  function applySharedNote(note) {
    const textarea = document.querySelector('[data-component="evidence-note"] textarea');
    if (textarea?.dataset.dirty === "true") return;
    state.progress.note = note;
    if (!textarea) return;
    textarea.value = note.content || "";
    const status = textarea.closest('[data-component="evidence-note"]')
      ?.querySelector('[data-role="note-status"]');
    if (status) setText(status, note.updated_at ? "同期済み" : "入力すると自動同期します");
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

  state.activeChapterId = firstCurrentChapter().id;
  renderChapter();
  const noteEvents = new EventSource("/api/note/events");
  noteEvents.addEventListener("message", (event) => {
    try {
      applySharedNote(JSON.parse(event.data));
    } catch (_error) {
      // 壊れたイベントは無視し、再接続後の初期イベントで復旧する。
    }
  });
  window.addEventListener("focus", refreshSharedNote);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshSharedNote();
  });
})();
