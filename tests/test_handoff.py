"""Smart Handoff request detection: multilingual high-precision unit tests."""

import unittest

from handoff import HUMAN_REQUESTED, detect_handoff_reason


class HandoffDetectionTests(unittest.TestCase):
    def test_uzbek_explicit_requests(self):
        messages = (
            "Assalomu alaykum, egasi bilan gaplashsam bo‘ladimi?",
            "Men operator bilan gaplashmoqchiman.",
            "Iltimos, meni operatorga ulang.",
            "Menejer bilan bog‘lanmoqchiman.",
            "Menga haqiqiy odam javob bersin.",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(detect_handoff_reason(message), HUMAN_REQUESTED)

    def test_english_requests(self):
        messages = (
            "I want to speak with a human.",
            "Please connect me to an agent.",
            "Can I talk to the owner?",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(detect_handoff_reason(message), HUMAN_REQUESTED)

    def test_russian_requests(self):
        messages = (
            "Можно поговорить с оператором?",
            "Соедините меня с менеджером, пожалуйста.",
            "Мне нужен человек.",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(detect_handoff_reason(message), HUMAN_REQUESTED)

    def test_regular_questions_do_not_escalate(self):
        messages = (
            "Salom, narx qancha?",
            "Operatoringiz soat nechada ishlaydi?",
            "When does your store open?",
            "Сколько стоит доставка?",
            "Menda bir savol bor.",
            "Assalomu alaykum.",
            "",
            None,
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(detect_handoff_reason(message))

    def test_explicit_refusal_not_escalated(self):
        messages = (
            "Men operator bilan gaplashishni xohlamayman.",
            "I don't want to speak with a human.",
            "Я не хочу поговорить с оператором.",
        )
        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(detect_handoff_reason(message))

    def test_non_string_input_ignored(self):
        self.assertIsNone(detect_handoff_reason(100))
        self.assertIsNone(detect_handoff_reason({}))


if __name__ == "__main__":
    unittest.main()
