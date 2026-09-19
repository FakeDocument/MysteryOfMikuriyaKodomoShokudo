(() => {
  "use strict";

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function renderInline(value) {
    return escapeHtml(value)
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  }

  function renderProse(lines) {
    if (!lines.length) return "";
    return `<p>${lines.map(renderInline).join("<br>")}</p>`;
  }

  function render(value) {
    const lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
    const output = [];
    let prose = [];
    let code = [];
    let language = "";
    let inFence = false;

    const flushProse = () => {
      if (prose.length) output.push(renderProse(prose));
      prose = [];
    };
    const flushCode = () => {
      const languageClass = language ? ` class="language-${language}"` : "";
      output.push(`<pre><code${languageClass}>${escapeHtml(code.join("\n"))}</code></pre>`);
      code = [];
      language = "";
    };

    lines.forEach((line) => {
      const fence = line.match(/^```([A-Za-z0-9_+-]*)\s*$/);
      if (fence) {
        if (inFence) {
          flushCode();
          inFence = false;
        } else {
          flushProse();
          language = fence[1];
          inFence = true;
        }
        return;
      }

      if (inFence) {
        code.push(line);
        return;
      }

      if (!line.trim()) {
        flushProse();
        return;
      }
      prose.push(line);
    });

    if (inFence) flushCode();
    flushProse();
    return output.join("");
  }

  window.NotebookMarkdown = Object.freeze({ render, renderInline });
})();
