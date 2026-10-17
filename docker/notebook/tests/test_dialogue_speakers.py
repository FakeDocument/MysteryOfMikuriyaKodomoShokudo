import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import content


class DialogueSpeakersTest(unittest.TestCase):
    def test_loaded_expressions_are_accepted_by_dialogue_validation(self):
        for speaker_id, speaker in content.DIALOGUE_SPEAKERS.items():
            for expression in speaker['avatars']:
                with self.subTest(speaker=speaker_id, expression=expression):
                    content._validate_dialogue(
                        [{'speaker': speaker_id, 'expression': expression, 'text': 'test'}],
                        'messages',
                    )

    def test_invalid_speaker_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            for speaker in (
                {'name': 'test', 'defaultExpression': 'missing', 'avatars': {'normal': 'test.png'}},
                {'name': 'test', 'defaultExpression': 'normal', 'avatars': {'normal': '../test.png'}},
                {'name': 'test', 'defaultExpression': 'normal', 'avatars': {'normal': 'missing.png'}},
            ):
                with self.subTest(speaker=speaker):
                    (data_dir / 'dialogue-speakers.json').write_text(json.dumps(
                        {'version': 1, 'speakers': {'test': speaker}}
                    ))
                    with patch.object(content, 'DATA_DIR', data_dir):
                        with self.assertRaises(content.ContentConfigurationError):
                            content._load_dialogue_speakers()
