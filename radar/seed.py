"""초기 유니버스: seed/refs_channels_verified_20261017.json 읽기."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import SEED_PATH

CID = re.compile(r"/channel/(UC[\w-]{22})$")


def load_seed(path: Path = SEED_PATH) -> tuple[dict[str, dict], list[dict]]:
    """반환: ({channel_id: {channel, group, subs}}, 제외 목록)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ok: dict[str, dict] = {}
    excluded: list[dict] = []
    for group, items in data.items():
        for it in items:
            m = CID.search(it.get("url") or "")
            if not m:
                excluded.append({"group": group, "q": it.get("q"), "channel": it.get("channel"),
                                 "reason": it.get("note") or "url이 channel/None 이거나 없음"})
                continue
            cid = m.group(1)
            if cid in ok:      # 같은 채널이 두 그룹에 있으면 첫 그룹 유지
                continue
            ok[cid] = {"channel": (it.get("channel") or "").strip(), "group": group, "subs": it.get("subs")}
    return ok, excluded
