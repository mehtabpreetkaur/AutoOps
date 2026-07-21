import unittest

from autoops.safety import check_content_safety


class SafetyTests(unittest.TestCase):
    def test_allows_operational_internal_email(self) -> None:
        result = check_content_safety("Escalate to payments-platform-oncall@example.internal")

        self.assertTrue(result.allowed)
        self.assertEqual([], result.findings)

    def test_blocks_external_or_customer_email(self) -> None:
        result = check_content_safety("Customer contact: customer@example.com")

        self.assertFalse(result.allowed)
        self.assertEqual("customer_or_external_email", result.findings[0].rule_id)

    def test_blocks_secret_like_assignment(self) -> None:
        result = check_content_safety("api_key=abc123456789")

        self.assertFalse(result.allowed)
        self.assertEqual("api_key_assignment", result.findings[0].rule_id)


if __name__ == "__main__":
    unittest.main()
