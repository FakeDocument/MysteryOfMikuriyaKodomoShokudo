import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"


class MarkdownRenderingTest(unittest.TestCase):
    def test_markdown_support_is_local_and_escapes_html(self):
        template = (APP_DIR / "templates" / "index.html").read_text(encoding="utf-8")
        script = (APP_DIR / "static" / "notebook.js").read_text(encoding="utf-8")
        markdown = (APP_DIR / "static" / "markdown.js").read_text(encoding="utf-8")
        main = (APP_DIR / "main.py").read_text(encoding="utf-8")

        self.assertLess(template.index("/markdown.js"), template.index("/notebook.js"))
        self.assertIn(
            'for filename in ("notebook.css", "markdown.js", "notebook.js")',
            main,
        )
        self.assertIn('replace(/[&<>"\']/g', markdown)
        self.assertIn(
            'replace(/\\*\\*([^*\\n]+)\\*\\*/g, "<strong>$1</strong>")',
            markdown,
        )
        self.assertIn('output.push(`<pre><code${languageClass}>', markdown)
        self.assertIn("setMarkdown(copy, entry.text)", script)
        self.assertNotIn('preview.dataset.role = "note-preview"', script)
        self.assertNotIn("setMarkdown(preview", script)
        self.assertNotIn("https://cdn", template)


if __name__ == "__main__":
    unittest.main()
