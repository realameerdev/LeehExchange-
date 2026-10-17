import unittest
from unittest.mock import patch

import app as app_module


class RevenueAndActivityTests(unittest.TestCase):
    def test_currency_parsers_require_explicit_currency_markers(self):
        self.assertEqual(app_module.parse_naira_amount("₦1,328"), 1328.0)
        self.assertEqual(app_module.parse_naira_amount("NGN 2,000.50"), 2000.5)
        self.assertEqual(app_module.parse_naira_amount("$42.00"), 0.0)
        self.assertEqual(app_module.parse_naira_amount("0.5 SOL"), 0.0)

        self.assertEqual(app_module.parse_usd_amount("$42.00"), 42.0)
        self.assertEqual(app_module.parse_usd_amount("USD 1,200.75"), 1200.75)
        self.assertEqual(app_module.parse_usd_amount("₦42,000"), 0.0)
        self.assertEqual(app_module.parse_usd_amount("0.5 SOL"), 0.0)

    def test_transaction_totals_keep_ngn_and_usd_separate(self):
        transactions = [
            {"Type": "Airtime", "Amount": "₦1,000", "Status": "Approved"},
            {"Type": "Data", "Amount": "NGN 750.50", "Status": "completed"},
            {"Type": "Buy", "Amount": "$12.50", "Status": "Approved"},
            {"Type": "Buy", "Amount": "USD 7.25", "Status": "completed"},
            # Pending, rejected, user-join, and crypto-quantity values are
            # not settled currency totals.
            {"Type": "Buy", "Amount": "$999", "Status": "pending"},
            {"Type": "Sell", "Amount": "₦5,000", "Status": "rejected"},
            {"Type": "User Join", "Amount": "₦10,000", "Status": "approved"},
            {"Type": "Sell", "Amount": "0.5 SOL", "Status": "approved"},
        ]

        naira, usd = app_module.transaction_totals(transactions)

        self.assertEqual(naira, 1750.5)
        self.assertEqual(usd, 19.75)
        self.assertEqual(naira + usd, 1770.25)

    def test_public_landing_activity_only_includes_approved_crypto_trades(self):
        transactions = [
            {
                "Type": "Buy",
                "Coin": "BTC",
                "Amount": "$10.00",
                "Status": "approved",
                "UserID": "buyer",
            },
            {
                "Type": "Sell",
                "Coin": "SOL",
                "Amount": "0.5 SOL",
                "Status": "Completed",
                "UserID": "seller",
            },
            {
                "Type": "Buy",
                "Coin": "ETH",
                "Amount": "$99.00",
                "Status": "pending",
                "UserID": "pending",
            },
            {
                "Type": "Sell",
                "Coin": "BTC",
                "Amount": "2 BTC",
                "Status": "rejected",
                "UserID": "rejected",
            },
        ]

        with patch.object(app_module, "load_transactions", return_value=transactions):
            response = app_module.app.test_client().get("/api/landing-stats")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["trading_volume_ngn"], 0.0)
        self.assertEqual(payload["trading_volume_usd"], 10.0)
        self.assertEqual(payload["combined_value"], 10.0)
        self.assertEqual(
            payload["crypto_volume"],
            [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "orders": 1,
                    "buy_usd": 10.0,
                    "sell_quantity": 0.0,
                },
                {
                    "symbol": "SOL",
                    "name": "Solana",
                    "orders": 1,
                    "buy_usd": 0.0,
                    "sell_quantity": 0.5,
                },
            ],
        )


class AdminAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.admin_config = {
            "admin_email": "owner@example.com",
            "admin_password": "owner-password",
            "sub_admins": [
                {
                    "id": "sub-1",
                    "status": "active",
                    "username": "operations",
                    "login_email": "operations@example.com",
                    "password": "sub-password",
                    "name": "Operations",
                    "role": "transaction_manager",
                    # Include the legacy grant to verify login strips it.
                    "permissions": ["dashboard", "transactions_view"],
                }
            ],
        }

    def test_sub_admin_is_routed_to_first_permitted_page_and_denied_dashboard(self):
        with patch.object(
            app_module, "load_admin_config", return_value=self.admin_config
        ):
            login_response = self.client.post(
                "/login",
                data={"email": "operations", "password": "sub-password"},
            )
            self.assertEqual(login_response.status_code, 302)
            self.assertEqual(login_response.headers["Location"], "/transactions")

            dashboard_response = self.client.get("/dashboard")

        self.assertEqual(dashboard_response.status_code, 403)
        self.assertIn(b"Access Denied", dashboard_response.data)

    def test_sub_admin_admin_entrypoint_uses_first_permitted_page(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
            session["is_super_admin"] = False
            session["admin_permissions"] = ["dashboard", "rates", "users"]
            session["sub_admin_id"] = "sub-1"

        with patch.object(
            app_module, "load_admin_config", return_value=self.admin_config
        ):
            response = self.client.get("/admin")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/users")


if __name__ == "__main__":
    unittest.main()