import unittest
from unittest.mock import patch

from services.ai_service import (
    BANNED_OUTREACH_PHRASES,
    _finalize_body_for_company_type,
    _finalize_subject_for_company_type,
    _sanitise_body,
)
from services.signature_service import ensure_signature


class MessageGenerationTests(unittest.TestCase):
    def test_client_body_removes_banned_spam_phrases(self):
        body = (
            "Your five-star reviews are great. This could boost conversions "
            "and pay for itself quickly with 100% better enquiry flow. "
            "Nothing will never fall through the cracks after a quick call."
        )

        cleaned = _finalize_body_for_company_type(body, "client")
        lower = cleaned.lower()

        for phrase in BANNED_OUTREACH_PHRASES:
            self.assertNotIn(phrase.lower(), lower)

    def test_client_subject_is_short_and_non_clickbait(self):
        subject, warnings = _finalize_subject_for_company_type(
            "Guaranteed 100% boost conversions for your business today",
            "client",
        )

        self.assertLessEqual(len(subject), 45)
        self.assertEqual(subject, "Website and enquiry flow")
        self.assertEqual(warnings, [])

    def test_deliverability_warning_lists_matched_terms(self):
        _, warnings = _sanitise_body("This is 100% guaranteed and urgent.")

        warning_text = "\n".join(warnings).lower()
        self.assertIn("deliverability terms in body", warning_text)
        self.assertIn("urgent", warning_text)

    def test_client_body_stays_under_reasonable_length(self):
        long_body = " ".join(["practical"] * 180)

        cleaned = _finalize_body_for_company_type(long_body, "client")

        self.assertLessEqual(len(cleaned.split()), 120)

    def test_client_signature_uses_the_configured_mailbox(self):
        values = {
            "CUSTOM_FROM_NAME": "Studio Ana",
            "CUSTOM_SMTP_USER": "ana@example.com",
        }

        with patch("services.profile_service.profile_identity", return_value=None), \
             patch("services.settings_service.get_raw", side_effect=lambda key: values.get(key, "")):
            body = ensure_signature("Hello", "client")

        self.assertTrue(body.endswith("Studio Ana\nana@example.com"))
        self.assertNotIn("http", body.lower())


if __name__ == "__main__":
    unittest.main()
