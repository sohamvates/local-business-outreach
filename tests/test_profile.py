import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.profile_service import (
    complete_setup,
    load_profile,
    mark_setup_started,
    needs_setup,
    profile_city_names,
    public_status,
    resolve_places,
    suggestion_items,
    update_places,
    save_profile,
)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.profile_path = root / "profile.json"
        self.env_path = root / ".env"
        self.env_path.write_text("", encoding="utf-8")
        self._old = {
            "OUTREACH_PROFILE_PATH": os.environ.get("OUTREACH_PROFILE_PATH"),
            "OUTREACH_ENV_FILE": os.environ.get("OUTREACH_ENV_FILE"),
        }
        os.environ["OUTREACH_PROFILE_PATH"] = str(self.profile_path)
        os.environ["OUTREACH_ENV_FILE"] = str(self.env_path)

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_empty_install_needs_setup(self):
        self.assertTrue(needs_setup())
        self.assertIsNone(profile_city_names())

    def test_existing_mailbox_skips_setup(self):
        self.env_path.write_text(
            "GMAIL_SMTP_USER=owner@example.com\nGMAIL_SMTP_PASSWORD=real-password\n",
            encoding="utf-8",
        )
        self.assertFalse(needs_setup())

    def test_completed_profile_supplies_cities_and_hides_secrets(self):
        save_profile({
            "completed": True,
            "country": "Portugal",
            "audience": "clients",
            "cities": [{"name": "Lisbon", "lat": 38.7, "lng": -9.1, "query": "Lisbon, Portugal"}],
            "niches": ["Dentists"],
            "sending_via": "custom",
            "identity": {
                "name": "Ana",
                "company": "Studio Ana",
                "email": "ana@example.com",
                "from_name": "Studio Ana",
                "signature": "Ana\nStudio Ana",
            },
        })
        self.assertFalse(needs_setup())
        self.assertEqual(profile_city_names(), ["Lisbon"])
        status = public_status()
        self.assertEqual(status["brand_name"], "Studio Ana")
        self.assertIn("Lisbon", status["client_search_title"])
        raw = self.profile_path.read_text(encoding="utf-8")
        self.assertNotIn("password", raw.lower())
        self.assertNotIn("api_key", raw.lower())

    def test_place_error_hides_the_key(self):
        class Response:
            def json(self):
                return {"status": "REQUEST_DENIED", "error_message": "rejected secret-key"}

        with patch("services.profile_service.httpx.get", return_value=Response()):
            with self.assertRaises(ValueError) as caught:
                resolve_places("Portugal", ["Lisbon"], "secret-key")
        self.assertNotIn("secret-key", str(caught.exception))
        self.assertIn("[key]", str(caught.exception))

    def test_country_must_be_a_country_and_city_must_be_inside_it(self):
        with patch("services.profile_service.httpx.get", side_effect=fake_places):
            with self.assertRaises(ValueError) as country:
                resolve_places("Melbourne", ["Lisbon"], "maps-test")
            self.assertIn("not a country", str(country.exception))

            with self.assertRaises(ValueError) as missing:
                resolve_places("Narnia", ["Lisbon"], "maps-test")
            self.assertIn("could not find", str(missing.exception).lower())

            with self.assertRaises(ValueError) as outside:
                resolve_places("Portugal", ["Paris"], "maps-test")
            self.assertIn("outside", str(outside.exception))

            found = resolve_places("Portugal", ["Lisbon", "Lisbon"], "maps-test")
            with self.assertRaises(ValueError) as wrong_state:
                resolve_places("Portugal", ["Lisbon"], "maps-test", ["Porto"])
            self.assertIn("not in Porto", str(wrong_state.exception))
        self.assertEqual(found["country_name"], "Portugal")
        self.assertEqual(found["country_code"], "PT")
        self.assertEqual(len(found["cities"]), 1)
        self.assertEqual(found["cities"][0]["formatted_address"], "Lisbon, Portugal")
        self.assertEqual(found["cities"][0]["lat"], 38.72)

    def test_finish_writes_profile_without_secrets(self):
        with patch("services.profile_service.httpx.get", side_effect=fake_places):
            result = complete_setup({
                "name": "Ana",
                "company": "Studio Ana",
                "role": "Founder",
                "country": "pt",
                "cities": ["Lisbon"],
                "audience": "both",
                "niches": ["Dentists"],
                "smtp_host": "mail.example.com",
                "smtp_port": "587",
                "smtp_user": "ana@example.com",
                "smtp_password": "super-secret-password",
                "from_name": "Studio Ana",
                "daily_limit": 20,
                "claude_api_key": "sk-ant-test",
                "google_maps_api_key": "maps-test",
                "signature": "Ana\nStudio Ana",
            })
        self.assertTrue(result["ok"], result)
        stored = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["country"], "Portugal")
        self.assertEqual(stored["cities"][0]["formatted_address"], "Lisbon, Portugal")
        self.assertIn("ana@example.com", stored["identity"]["signature"])
        dumped = json.dumps(stored)
        self.assertNotIn("super-secret-password", dumped)
        self.assertNotIn("sk-ant-test", dumped)
        self.assertNotIn("maps-test", dumped)
        env_text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("super-secret-password", env_text)
        self.assertIn("DAILY_SEND_LIMIT=20", env_text)

    def test_failed_finish_keeps_the_assistant_open(self):
        with patch("services.profile_service.httpx.get", side_effect=fake_places):
            result = complete_setup({
                "name": "Ana",
                "company": "Studio Ana",
                "country": "Narnia",
                "cities": ["Lisbon"],
                "audience": "clients",
                "niches": ["Dentists"],
                "smtp_host": "mail.example.com",
                "smtp_port": "587",
                "smtp_user": "ana@example.com",
                "smtp_password": "super-secret-password",
                "daily_limit": 20,
                "claude_api_key": "sk-ant-test",
                "google_maps_api_key": "maps-test",
            })
        self.assertFalse(result["ok"])
        self.assertTrue(needs_setup())
        self.assertNotIn("super-secret-password", self.profile_path.read_text(encoding="utf-8"))

    def test_suggestions_keep_one_state_and_cities_inside_it(self):
        states = suggestion_items("state", [
            {"types": ["locality"], "structured_formatting": {"main_text": "Campinas"}},
            {
                "types": ["administrative_area_level_1", "political"],
                "structured_formatting": {"main_text": "São Paulo", "secondary_text": "Brazil"},
            },
        ])
        self.assertEqual([item["name"] for item in states], ["São Paulo"])
        cities = suggestion_items("city", [
            {
                "types": ["locality", "political"],
                "structured_formatting": {"main_text": "Campinas", "secondary_text": "São Paulo, Brazil"},
            },
            {
                "types": ["locality", "political"],
                "structured_formatting": {"main_text": "Rio de Janeiro", "secondary_text": "Rio de Janeiro, Brazil"},
            },
        ], "São Paulo")
        self.assertEqual([item["name"] for item in cities], ["Campinas"])

    def test_places_cannot_be_edited_before_setup(self):
        result = update_places("Portugal", [{"city": "Lisbon", "state": "Lisbon"}], "maps-test")
        self.assertFalse(result["ok"])

    def test_existing_mailbox_is_not_marked_in_progress(self):
        self.env_path.write_text(
            "GMAIL_SMTP_USER=owner@example.com\nGMAIL_SMTP_PASSWORD=real-password\n",
            encoding="utf-8",
        )
        mark_setup_started()
        self.assertFalse(self.profile_path.exists())
        self.assertFalse(needs_setup())


def fake_places(url, params=None, timeout=None):
    params = params or {}
    query = params.get("input") or ""
    place_id = params.get("place_id") or ""
    if place_id:
        return FakeResponse(PLACE_DETAILS[place_id])
    place_id = FIND_IDS.get(query)
    if not place_id:
        return FakeResponse({"status": "ZERO_RESULTS", "candidates": []})
    return FakeResponse({"status": "OK", "candidates": [{"place_id": place_id}]})


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _details(name, address, lat, lng, types, country_name, country_code, admin_name=""):
    components = [
        {"long_name": country_name, "short_name": country_code, "types": ["country", "political"]},
    ]
    if admin_name:
        components.append({
            "long_name": admin_name,
            "short_name": admin_name,
            "types": ["administrative_area_level_1", "political"],
        })
    return {
        "status": "OK",
        "result": {
            "name": name,
            "formatted_address": address,
            "geometry": {"location": {"lat": lat, "lng": lng}},
            "types": types,
            "address_components": components,
        },
    }


FIND_IDS = {
    "Portugal": "country-pt",
    "pt": "country-pt",
    "Melbourne": "city-melbourne",
    "Lisbon, Portugal": "city-lisbon",
    "Lisbon, Porto, Portugal": "city-lisbon",
    "Paris, Portugal": "city-paris",
    "Narnia": "",
}

PLACE_DETAILS = {
    "country-pt": _details("Portugal", "Portugal", 39.4, -8.2, ["country", "political"], "Portugal", "PT"),
    "city-lisbon": _details("Lisbon", "Lisbon, Portugal", 38.72, -9.14, ["locality", "political"], "Portugal", "PT", "Lisbon"),
    "city-paris": _details("Paris", "Paris, France", 48.85, 2.35, ["locality", "political"], "France", "FR"),
    "city-melbourne": _details(
        "Melbourne", "Melbourne VIC, Australia", -37.81, 144.96,
        ["locality", "political"], "Australia", "AU",
    ),
}


if __name__ == "__main__":
    unittest.main()
