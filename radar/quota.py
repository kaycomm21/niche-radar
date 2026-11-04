"""쿼터 로거: 모든 API 호출의 유닛을 quota_log 에 기록하고, 하루 예산을 넘기기 전에 멈춘다."""
from __future__ import annotations

import sqlite3

# YouTube Data API v3 유닛 비용 (list 계열 1, search 100)
UNIT_COST = {
    "videos.list": 1, "channels.list": 1, "playlistItems.list": 1,
    "commentThreads.list": 1, "search.list": 100,
}


class BudgetExceeded(RuntimeError):
    pass


class Quota:
    def __init__(self, con: sqlite3.Connection, date: str, budget: int, job: str = "daily"):
        self.con, self.date, self.budget, self.job = con, date, budget, job

    def used_today(self) -> int:
        r = self.con.execute("SELECT COALESCE(SUM(units),0) FROM quota_log WHERE date=?", (self.date,)).fetchone()
        return int(r[0])

    def calls_today(self, endpoint: str) -> int:
        r = self.con.execute("SELECT COALESCE(SUM(calls),0) FROM quota_log WHERE date=? AND endpoint=?",
                             (self.date, endpoint)).fetchone()
        return int(r[0])

    def remaining(self) -> int:
        return self.budget - self.used_today()

    def spend(self, endpoint: str) -> None:
        """호출 '전에' 부른다. 예산을 넘기면 BudgetExceeded (호출하지 않음)."""
        cost = UNIT_COST[endpoint]
        if self.used_today() + cost > self.budget:
            raise BudgetExceeded(f"{endpoint} 호출 시 하루 예산 {self.budget} 초과 — 수집 중단")
        self.con.execute(
            """INSERT INTO quota_log(date, job, endpoint, units, calls) VALUES (?,?,?,?,1)
               ON CONFLICT(date, job, endpoint) DO UPDATE SET units=units+excluded.units, calls=calls+1""",
            (self.date, self.job, endpoint, cost))
