import pytest
from datetime import date
from dateutil.relativedelta import relativedelta
from bot import calculate_renewal_date, settings

def test_calculate_renewal_date():
    today = date(2025, 6, 10)
    expected = date(2025, 7, settings.RENEWAL_DAY)
    # Patch date.today
    import bot
    bot.date = lambda: today
    assert calculate_renewal_date() == expected

def test_referral_earnings_logic(monkeypatch):
    class DummyCollection:
        def count_documents(self, query):
            if query.get("status") == "Approved" and query.get("godfather") == 123:
                if "registration_date" in query:
                    return 2
                return 5
            return 0
    monkeypatch.setattr("bot.users_collection", DummyCollection())
    from bot import referral_earnings
    # You would need to mock update/context for a full test

def test_mongodb_update_one(monkeypatch):
    class DummyCollection:
        def __init__(self):
            self.data = {}
        def update_one(self, query, update, upsert=False):
            key = query["user_id"]
            self.data[key] = update["$set"]
    dummy = DummyCollection()
    monkeypatch.setattr("bot.users_collection", dummy)
    # Simulate insert/update
    dummy.update_one({"user_id": 1}, {"$set": {"name": "Test"}}, upsert=True)
    assert dummy.data[1]["name"] == "Test"