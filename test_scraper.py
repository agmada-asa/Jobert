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

        with self.assertRaisesRegex(
            scraper.TrackrApiError, "expected a programmes list"
        ):
            scraper.scrape_trackr()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_programme_fields_are_renamed(self, get: Mock):
        response = Mock()
        response.json.return_value = {
            "programmes": [{"programmeId": "programme-1", "label": "Intern"}]
        }
        get.return_value = response

        with self.assertRaisesRegex(scraper.TrackrApiError, "no usable id"):
            scraper.scrape_trackr()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_every_programme_list_is_empty(self, get: Mock):
        response = Mock()
        response.json.return_value = {"programmes": [], "groups": []}
        get.return_value = response

        with self.assertRaisesRegex(scraper.TrackrApiError, "empty programmes lists"):
            scraper.scrape_trackr()


class ApiHealthMonitorTests(unittest.TestCase):
    def setUp(self):
        self.state = {"status": "healthy", "recovery_notified": True}
        load_patcher = patch(
            "scraper._load_api_health", side_effect=lambda: dict(self.state)
        )
        save_patcher = patch(
            "scraper._save_api_health", side_effect=self._save_health_state
        )
        load_patcher.start()
        save_patcher.start()
        self.addCleanup(load_patcher.stop)
        self.addCleanup(save_patcher.stop)

    def _save_health_state(self, state):
        self.state = dict(state)

    @patch("scraper.send_telegram_message", return_value=True)
    def test_sends_one_alert_for_a_repeated_failure(self, send: Mock):
        issues = ["season 2027: expected a programmes list"]

        scraper._record_api_failure(issues)
        scraper._record_api_failure(issues)

        send.assert_called_once()
        self.assertEqual(self.state["status"], "unhealthy")
        self.assertTrue(self.state["notified"])

    @patch("scraper.send_telegram_message", return_value=True)
    def test_new_failure_shape_sends_a_new_alert(self, send: Mock):
        scraper._record_api_failure(["season 2027: invalid JSON"])
        scraper._record_api_failure(["season 2027: expected a programmes list"])

        self.assertEqual(send.call_count, 2)

    @patch("scraper.send_telegram_message", return_value=True)
    def test_sends_one_recovery_message(self, send: Mock):
        scraper._record_api_failure(["season 2027: invalid JSON"])

        scraper._record_api_recovery()
        scraper._record_api_recovery()

        self.assertEqual(send.call_count, 2)
        self.assertEqual(self.state["status"], "healthy")
        self.assertTrue(self.state["recovery_notified"])


if __name__ == "__main__":
    unittest.main()
