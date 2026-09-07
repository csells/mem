"""Local snapshot adapter for the LedgerLake transactions endpoint."""

from datetime import datetime


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class LedgerLake:
    def __init__(self, transactions):
        self.transactions = transactions

    def list_transactions(self, *, created_from, created_to):
        low = parse_timestamp(created_from)
        high = parse_timestamp(created_to)
        rows = [
            row for row in self.transactions
            if low <= parse_timestamp(row["posted_at"]) < high
        ]
        return sorted(rows, key=lambda row: (parse_timestamp(row["posted_at"]), row["id"]))
