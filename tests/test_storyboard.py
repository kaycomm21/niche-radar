from radar.storyboard import meta, parse, storyboard

MD = """# ⓒ 대본 09 — 테스트 제목
> 채널: 경제적자유구역 · 롱폼

---

## [0:00] 후킹
(B롤: 골목, 휴대폰)

첫 문장입니다. **강조**
(자막: 이 영상은 투자 권유가 아닙니다)

## [1:30] 본론
두번째 섹션 내레이션.

---
## 제작 메모
| x | y |
"""


def test_parse_and_build():
    d = parse(MD)
    assert d["title"] == "테스트 제목" and d["channel"] == "경제적자유구역"
    assert [s["start_s"] for s in d["sections"]] == [0, 90]
    assert d["sections"][0]["broll"] == ["골목", "휴대폰"]
    assert d["sections"][0]["captions"] == ["이 영상은 투자 권유가 아닙니다"]
    assert "강조" in d["sections"][0]["narration"][0] and "**" not in d["sections"][0]["narration"][0]
    sb = storyboard(d)
    assert len(sb["shots"]) == 3 and "no logos" in sb["shots"][0]["prompt_en"]
    m = meta(d, ["A", "B"], ["t1", "t2"], "면책")
    assert m["chapters"][0].startswith("0:00") and m["privacy"] == "private" and "면책" in m["description"]
