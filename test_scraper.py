import html
import json
import re
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests
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
        item = {**PROGRAMME, "openingDate": "2026-09-14T00:00:00.000Z",
                "closingDate": "2026-09-15T00:00:00.000Z"}
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
    @patch.object(scraper, "TRACKR_SEASONS", ("2026",))
    @patch("scraper.requests.get")
    def test_retries_a_timeout_and_uses_the_recovered_response(
        self, get: Mock, sleep: Mock
    ):
        response = Mock()
        response.json.return_value = {"programmes": [PROGRAMME]}
        get.side_effect = [requests.Timeout("temporary timeout"), response]
        with patch.object(scraper, "TRACKR_PROGRAMME_TYPES", scraper.TRACKR_PROGRAMME_TYPES[:1]):
            jobs = scraper.scrape_trackr()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch.object(scraper, "TRACKR_SEASONS", ("2026",))
    @patch("scraper.requests.get", side_effect=requests.Timeout("still timed out"))
    def test_still_fails_after_bounded_timeout_retries(
        self, get: Mock, sleep: Mock
    ):
        with patch.object(scraper, "TRACKR_PROGRAMME_TYPES", scraper.TRACKR_PROGRAMME_TYPES[:1]):
            with self.assertRaisesRegex(scraper.TrackrApiError, "still timed out"):
                scraper.scrape_trackr()

        self.assertEqual(get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

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
                    "opening_date": PROGRAMME["openingDate"],
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


class IndividualAlertTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            {"id": f"trackr_{index}", "role": f"Placement {index}",
             "company": "Example & Co", "link": "https://example.com/apply?a=1&b=2",
             "label": "Industrial Placement", "emoji": "🏗️",
             "opening_date": "2026-09-09"}
            for index in range(17)
        ]

    @patch("scraper.time.sleep")
    @patch("scraper._record_api_recovery")
    @patch("scraper.save_seen_jobs")
    @patch("scraper.send_telegram_message", return_value=True)
    @patch("scraper._is_active", return_value=True)
    @patch("scraper.scrape_trackr")
    @patch("scraper.load_seen_jobs", return_value=[])
    def test_large_run_is_paced_and_capped_at_15_individual_alerts(
        self, load: Mock, scrape: Mock, active: Mock, send: Mock,
        save: Mock, recover: Mock, sleep: Mock
    ):
        scrape.return_value = self.jobs
        scraper.run()

        self.assertEqual(send.call_count, 15)
        self.assertIn("🏗️ <b>Placement 0</b>", send.call_args_list[0].args[0])
        self.assertIn("Example &amp; Co", send.call_args_list[0].args[0])
        self.assertIn("a=1&amp;b=2", send.call_args_list[0].args[0])
        save.assert_called_once_with([job["id"] for job in self.jobs[:15]])
        self.assertEqual(sleep.call_count, 14)
        sleep.assert_any_call(2)

    @patch("scraper._record_api_recovery")
    @patch("scraper.save_seen_jobs")
    @patch("scraper.send_telegram_message", return_value=True)
    @patch("scraper._is_active", return_value=True)
    @patch("scraper.scrape_trackr")
    @patch("scraper.load_seen_jobs", return_value=[])
    def test_even_one_new_listing_sends_its_emoji_alert(
        self, load: Mock, scrape: Mock, active: Mock, send: Mock,
        save: Mock, recover: Mock
    ):
        scrape.return_value = self.jobs[:1]
        scraper.run()

        send.assert_called_once()
        self.assertIn("🏗️ <b>Placement 0</b>", send.call_args.args[0])
        self.assertIn("🏢 <i>Example &amp; Co</i>", send.call_args.args[0])
        self.assertIn("🔗 <a href=", send.call_args.args[0])
        save.assert_called_once_with(["trackr_0"])

    @patch("scraper._record_api_recovery")
    @patch("scraper.save_seen_jobs")
    @patch("scraper.send_telegram_message", return_value=True)
    @patch("scraper._is_active", return_value=True)
    @patch("scraper.scrape_trackr")
    @patch("scraper.load_seen_jobs", return_value=[])
    def test_individual_alerts_are_ordered_by_opening_date_newest_first(
        self, load: Mock, scrape: Mock, active: Mock, send: Mock,
        save: Mock, recover: Mock
    ):
        scrape.return_value = [
            self.jobs[0],
            {**self.jobs[1], "opening_date": "2026-09-15"},
        ]
        scraper.run()

        self.assertIn("Placement 1", send.call_args_list[0].args[0])
        self.assertIn("Placement 0", send.call_args_list[1].args[0])
        save.assert_called_once_with(["trackr_1", "trackr_0"])


class BurstSummaryTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "burst.json"
            shutil.copyfile(scraper.BURST_SUMMARY_FILE, target)
            self.initial_state = json.loads(target.read_text(encoding="utf-8"))
            self.initial_state["sent_at"] = None

    def test_snapshot_is_the_19_burst_placements_and_fits_one_message(self):
        items = self.initial_state["items"]
        self.assertEqual(len(items), 19)
        self.assertEqual(len({item["id"] for item in items}), 19)
        self.assertTrue({item["id"] for item in items}.issubset(scraper.load_seen_jobs()))
        message = scraper.format_burst_summary(items)
        visible = html.unescape(re.sub(r"<[^>]+>", "", message))
        self.assertLessEqual(len(visible), 4096)
        self.assertIn("AWE, Year in Industry", message)
        self.assertIn("closes 20 Sep", message)

    @patch("scraper._is_open_programme", return_value=True)
    @patch("scraper.send_telegram_message", return_value=True)
    def test_explicit_dispatch_sends_once_and_records_success(
        self, send: Mock, eligible: Mock
    ):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "burst.json"
            target.write_text(json.dumps(self.initial_state), encoding="utf-8")
            with patch.object(scraper, "BURST_SUMMARY_FILE", str(target)):
                scraper.send_burst_summary()
                scraper.send_burst_summary()
            send.assert_called_once()
            self.assertIsNotNone(json.loads(target.read_text())["sent_at"])

    @patch("scraper._is_open_programme", return_value=True)
    @patch("scraper.send_telegram_message", return_value=False)
    def test_failed_send_remains_pending(self, send: Mock, eligible: Mock):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "burst.json"
            target.write_text(json.dumps(self.initial_state), encoding="utf-8")
            with patch.object(scraper, "BURST_SUMMARY_FILE", str(target)):
                with self.assertRaisesRegex(RuntimeError, "Could not send"):
                    scraper.send_burst_summary()
            self.assertIsNone(json.loads(target.read_text())["sent_at"])


class TelegramDeliveryTests(unittest.TestCase):
    @patch.object(scraper, "TELEGRAM_TOKEN", "test-token")
    @patch.object(scraper, "CHAT_ID", "test-chat")
    @patch("scraper.requests.post")
    def test_http_200_without_api_confirmation_is_not_recorded(self, post: Mock):
        post.return_value.json.return_value = {"ok": False}
        self.assertFalse(scraper.send_telegram_message("Test"))

    @patch.object(scraper, "TELEGRAM_TOKEN", "test-token")
    @patch.object(scraper, "CHAT_ID", "test-chat")
    @patch("scraper.requests.post")
    def test_confirmed_telegram_response_counts_as_sent(self, post: Mock):
        post.return_value.json.return_value = {"ok": True, "result": {}}
        self.assertTrue(scraper.send_telegram_message("Test"))


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
