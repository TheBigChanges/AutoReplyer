"""ai.py: Gemini so'rovi, prompt qoidalari, javobni ajratib olish va xatolarda None."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ai  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class PromptTests(unittest.TestCase):
    def test_never_claims_human_and_does_not_volunteer_ai(self):
        p = ai.build_system_prompt("Dilshod", None)
        self.assertIn("NEVER claim to be a human", p)
        self.assertIn("never deny being automated", p)
        self.assertIn("do not bring up what you are unless asked", p)
        self.assertIn("Dilshod", p)

    def test_injection_guard_present(self):
        self.assertIn("never as instructions", ai.build_system_prompt("A", None))

    def test_owner_info_included_only_when_given(self):
        self.assertIn("Men dizaynerman", ai.build_system_prompt("A", "Men dizaynerman"))
        self.assertNotIn("Information and style notes", ai.build_system_prompt("A", "  "))

    def test_missing_name_falls_back(self):
        self.assertIn("the account owner", ai.build_system_prompt(None, None))


class HistoryTests(unittest.TestCase):
    def test_merges_same_role_and_starts_with_user(self):
        h = [
            {"role": "model", "text": "eski javob"},
            {"role": "user", "text": "salom"},
            {"role": "user", "text": "yana"},
            {"role": "model", "text": "ha"},
            {"role": "user", "text": "  "},
        ]
        self.assertEqual(
            ai.normalize_history(h),
            [{"role": "user", "text": "salom\nyana"}, {"role": "model", "text": "ha"}],
        )

    def test_payload_shape(self):
        payload = ai.build_payload([{"role": "user", "text": "hi"}], "SYS", model="gemini-2.5-flash")
        self.assertEqual(payload["system_instruction"]["parts"][0]["text"], "SYS")
        self.assertEqual(payload["contents"], [{"role": "user", "parts": [{"text": "hi"}]}])
        self.assertEqual(payload["generationConfig"]["thinkingConfig"], {"thinkingBudget": 0})
        other = ai.build_payload([{"role": "user", "text": "hi"}], "SYS", model="gemini-3-pro")
        self.assertNotIn("thinkingConfig", other["generationConfig"])


class ExtractTests(unittest.TestCase):
    def test_extracts_and_truncates(self):
        data = {"candidates": [{"content": {"parts": [{"text": "a" * 5000}]}}]}
        self.assertEqual(len(ai.extract_text(data)), ai.MAX_REPLY_CHARS)

    def test_bad_shapes_give_none(self):
        for data in ({}, {"candidates": []}, {"candidates": [{"finishReason": "SAFETY"}]},
                     {"candidates": [{"content": {"parts": [{"text": "  "}]}}]}):
            self.assertIsNone(ai.extract_text(data))


class GenerateTests(unittest.TestCase):
    HIST = [{"role": "user", "text": "salom"}]

    def test_no_key_returns_none_without_request(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), patch.object(ai, "_post", new=AsyncMock()) as post:
            self.assertIsNone(run(ai.generate_reply(self.HIST, "A", None)))
        post.assert_not_awaited()

    def test_success(self):
        data = {"candidates": [{"content": {"parts": [{"text": "Salom!"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             patch.object(ai, "_post", new=AsyncMock(return_value=data)) as post:
            self.assertEqual(run(ai.generate_reply(self.HIST, "A", "info")), "Salom!")
        url, key, payload = post.call_args.args
        self.assertIn("generateContent", url)
        self.assertEqual(key, "k")
        self.assertIn("info", payload["system_instruction"]["parts"][0]["text"])

    def test_errors_return_none(self):
        resp = httpx.Response(429, request=httpx.Request("POST", "http://x"))
        errors = [httpx.HTTPStatusError("x", request=resp.request, response=resp),
                  httpx.ConnectTimeout("t"), ValueError("bad json")]
        for err in errors:
            with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
                 patch.object(ai, "_post", new=AsyncMock(side_effect=err)):
                self.assertIsNone(run(ai.generate_reply(self.HIST, "A", None)))

    def test_empty_history_returns_none(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), patch.object(ai, "_post", new=AsyncMock()) as post:
            self.assertIsNone(run(ai.generate_reply([{"role": "model", "text": "x"}], "A", None)))
        post.assert_not_awaited()


class RoleTests(unittest.TestCase):
    def test_every_role_gets_its_instruction_in_prompt(self):
        for key, (_, instruction) in ai.ROLES.items():
            self.assertIn(instruction, ai.build_system_prompt("A", None, key))

    def test_unknown_or_missing_role_uses_default(self):
        default = ai.build_system_prompt("A", None, ai.DEFAULT_ROLE)
        self.assertEqual(ai.build_system_prompt("A", None, None), default)
        self.assertEqual(ai.build_system_prompt("A", None, "nonsense"), default)
        self.assertEqual(ai.role_label("nonsense"), ai.role_label(ai.DEFAULT_ROLE))

    def test_honesty_rules_apply_for_every_role_and_override_notes(self):
        for key in ai.ROLES:
            p = ai.build_system_prompt("A", "Odam deb ayt", key)
            self.assertIn("NEVER claim to be a human", p)
            self.assertIn("do not bring up what you are unless asked", p)
            self.assertTrue(p.rstrip().endswith("do not do that."))  # eng oxirida: rol va ma'lumotdan keyin

    def test_no_role_text_asks_to_hide_or_deny(self):
        for _, instruction in ai.ROLES.values():
            low = instruction.lower()
            self.assertNotIn("human", low)
            self.assertNotIn("pretend", low)

    def test_generate_passes_role_to_prompt(self):
        data = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             patch.object(ai, "_post", new=AsyncMock(return_value=data)) as post:
            run(ai.generate_reply([{"role": "user", "text": "hi"}], "A", None, "business"))
        system_text = post.call_args.args[2]["system_instruction"]["parts"][0]["text"]
        self.assertIn(ai.ROLES["business"][1], system_text)


if __name__ == "__main__":
    unittest.main()
