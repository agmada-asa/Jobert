import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

import scraper


PROGRAMME = {
    "id": "programme-1",
    "name": "Software Engineering Internship",
    "url": "https://example.com/apply",
    "categories": ["Software Engineering"],
    "openingDate": datetime.now(timezone.utc).date().isoformat(),
    "closingDate": None,
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


class ProgrammeEligibilityTests(unittest.TestCase):
    today = date(2026, 9, 15)

    def test_open_with_no_known_deadline(self):
        item = {**PROGRAMME, "openingDate": "2026-09-14T00:00:00.000Z"}
        self.assertTrue(scraper._is_open_programme(item, self.today))

    def test_old_opening_with_no_deadline_is_not_assumed_live(self):
        item = {**PROGRAMME, "openingDate": "2025-09-14T00:00:00.000Z"}
        self.assertFalse(scraper._is_open_programme(item, self.today))

    def test_deadline_is_inclusive(self):
        item = {**PROGRAMME, "closingDate": "2026-09-15T00:00:00.000Z"}
        self.assertTrue(scraper._is_open_programme(item, self.today))

    def test_closed_programme_with_reachable_url_is_rejected(self):
        item = {**PROGRAMME, "closingDate": "2026-09-14T00:00:00.000Z"}
        self.assertFalse(scraper._is_open_programme(item, self.today))

    def test_future_or_unconfirmed_opening_is_rejected(self):
        for value in ("2026-09-16T00:00:00.000Z", None, "invalid"):
            with self.subTest(opening=value):
                item = {**PROGRAMME, "openingDate": value}
                self.assertFalse(scraper._is_open_programme(item, self.today))

    def test_malformed_closing_date_and_explicit_closed_status_are_rejected(self):
        for changes in ({"closingDate": "bad"}, {"status": "closed"}):
            with self.subTest(changes=changes):
                self.assertFalse(
                    scraper._is_open_programme({**PROGRAMME, **changes}, self.today)
                )

    def test_normaliser_skips_closed_and_unopened_placements(self):
        placement = next(
            kind for kind in scraper.TRACKR_PROGRAMME_TYPES
            if kind.type == "industrial-placements"
        )
        for changes in (
            {"closingDate": "2020-09-02T00:00:00.000Z"},
            {"openingDate": None},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(
                    scraper._normalise_trackr_job({**PROGRAMME, **changes}, placement)
                )


@patch("scraper.time.sleep")
class ScrapeTrackrTests(unittest.TestCase):
    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_scrapes_current_trackr_response(self, get: Mock, sleep: Mock):
        response = Mock()
        response.json.return_value = {"programmes": [PROGRAMME], "groups": []}
        get.return_value = response

        jobs = scraper.scrape_trackr()

        # The same programme id is returned for every mocked request (one per
        # programme type), so dedup keeps only the first — summer-internships.
        self.assertEqual(
            jobs,
            [
                {
                    "id": "trackr_programme-1",
                    "role": "Software Engineering Internship",
                    "company": "Example Ltd",
                    "link": "https://example.com/apply",
                    "label": "Internship",
                    "emoji": "🆕",
                }
            ],
        )
        self.assertEqual(
            response.raise_for_status.call_count, len(scraper.TRACKR_PROGRAMME_TYPES)
        )

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_every_response_has_an_unsupported_shape(
        self, get: Mock, sleep: Mock
    ):
        response = Mock()
        response.json.return_value = {"groups": []}
        get.return_value = response

        with self.assertRaisesRegex(
            scraper.TrackrApiError, "expected a programmes list"
        ):
            scraper.scrape_trackr()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_programme_fields_are_renamed(self, get: Mock, sleep: Mock):
        response = Mock()
        response.json.return_value = {
            "programmes": [{"programmeId": "programme-1", "label": "Intern"}]
        }
        get.return_value = response

        with self.assertRaisesRegex(scraper.TrackrApiError, "no usable id"):
            scraper.scrape_trackr()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_opening_date_field_disappears(self, get: Mock, sleep: Mock):
        response = Mock()
        response.json.return_value = {
            "programmes": [{key: value for key, value in PROGRAMME.items()
                            if key != "openingDate"}]
        }
        get.return_value = response

        with self.assertRaisesRegex(scraper.TrackrApiError, "openingDate"):
            scraper.scrape_trackr()

    @patch.object(scraper, "TRACKR_SEASONS", ("2027",))
    @patch("scraper.requests.get")
    def test_fails_when_every_programme_list_is_empty(self, get: Mock, sleep: Mock):
        response = Mock()
        response.json.return_value = {"programmes": [], "groups": []}
        get.return_value = response

        with self.assertRaisesRegex(scraper.TrackrApiError, "empty programmes lists"):
            scraper.scrape_trackr()


class NotificationBatchTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            {"id": f"trackr_{index}", "role": f"Placement {index}",
             "company": "Example & Co", "link": "https://example.com/apply?a=1&b=2",
             "label": "Industrial Placement"}
            for index in range(15)
        ]

    @patch("scraper.time.sleep")
    @patch("scraper._record_api_recovery")
    @patch("scraper.save_seen_jobs")
    @patch("scraper.send_telegram_message", side_effect=[False, True])
    @patch("scraper._is_active", return_value=True)
    @patch("scraper.scrape_trackr")
    @patch("scraper.load_seen_jobs", return_value=[])
    def test_catch_up_digests_only_mark_successfully_sent_jobs(
        self, load: Mock, scrape: Mock, active: Mock, send: Mock,
        save: Mock, recover: Mock, sleep: Mock
    ):
        scrape.return_value = self.jobs
        scraper.run()

        self.assertEqual(send.call_count, 2)
        self.assertIn("1-10 of 15", send.call_args_list[0].args[0])
        self.assertIn("11-15 of 15", send.call_args_list[1].args[0])
        self.assertIn("Example &amp; Co", send.call_args_list[0].args[0])
        self.assertIn("a=1&amp;b=2", send.call_args_list[0].args[0])
        save.assert_called_once_with([job["id"] for job in self.jobs[10:]])
        sleep.assert_called_once_with(2)


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
