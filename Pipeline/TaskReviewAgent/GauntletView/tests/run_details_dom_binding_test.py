"""Component regression: rendered project fields must have real DOM targets."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids.extend(value for key, value in attrs if key == 'id')


class RunDetailsDomTests(unittest.TestCase):
    def test_every_project_field_has_text_and_copy_button(self):
        document = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        parser = IdParser()
        parser.feed(document)
        function = document.split('function renderRunDetails(', 1)[1].split('function updateLegend', 1)[0]
        fields = re.findall(r"\['([a-z]+)', '[^']+', run\.", function)
        self.assertIn('runtime', fields)
        self.assertGreaterEqual(len(fields), 4)
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(parser.ids.count('run-' + field), 1)
                self.assertEqual(parser.ids.count('copy-run-' + field), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
