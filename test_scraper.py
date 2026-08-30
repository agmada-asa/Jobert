import unittest
from unittest.mock import Mock, patch

import scraper


PROGRAMME = {
    "id": "programme-1",
    "name": "Software Engineering Internship",
    "url": "https://example.com/apply",
    "categories": ["Software Engineering"],
    "company": {"id": "example", "name": "Example Ltd"},
}


class ExtractProgrammesTests(unittest.TestCase):
    def test_extracts_programmes_from_current_response(self):
        response = {"programmes": [PROGRAMME], "groups": []}

        self.assertEqual(scraper._extract_programmes(response), [PROGRAMME])

    def test_accepts_legacy_list_response(self):
        self.assertEqual(scraper._extract_programmes([PROGRAMME]), [PROGRAMME])

    def test_rejects_an_object_without_a_programmes_list(self):
        self.assertIsNone(scraper._extract_programmes({"programmes": {}}))


class ScrapeTrackrTests(unittest.TestCase):
    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_scrapes_current_trackr_response(self, get: Mock):
        response = Mock()
        response.json.return_value = {"programmes": [PROGRAMME], "groups": []}
        get.return_value = response

        jobs = scraper.scrape_trackr()

        self.assertEqual(
            jobs,
            [
                {
                    "id": "trackr_programme-1",
                    "role": "Software Engineering Internship",
                    "company": "Example Ltd",
                    "link": "https://example.com/apply",
                }
            ],
        )
        response.raise_for_status.assert_called_once_with()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_every_response_has_an_unsupported_shape(self, get: Mock):
        response = Mock()
        response.json.return_value = {"groups": []}
        get.return_value = response

        with self.assertRaisesRegex(RuntimeError, "no usable programme responses"):
            scraper.scrape_trackr()


if __name__ == "__main__":
    unittest.main()
