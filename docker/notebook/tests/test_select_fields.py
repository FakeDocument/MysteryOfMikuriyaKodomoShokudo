import unittest

from app.content import ContentConfigurationError, _validate_question_inputs


class SelectFieldsTest(unittest.TestCase):
    def question(self, options):
        return {"answer_fields": [
            {"id": "choice", "label": "Choice", "placeholder": "Choose", "input_mode": "select", "options": options},
            {"id": "other", "label": "Other", "placeholder": "Text", "input_mode": "text"},
        ]}

    def test_accepts_distinct_choices(self):
        _validate_question_inputs(self.question(["a", "b"]), "example")

    def test_rejects_invalid_choices(self):
        for options in (None, [], ["a"], ["a", "a"], ["a", ""], ["a", 1]):
            with self.subTest(options=options), self.assertRaises(ContentConfigurationError):
                _validate_question_inputs(self.question(options), "example")
