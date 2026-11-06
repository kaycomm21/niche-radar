import json

from radar import blog, gtrends

RSS = """<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>금리 인상</title><ht:approx_traffic>20000+</ht:approx_traffic><pubDate>Wed, 5 Nov 2026 01:00:00 +0900</pubDate>
<ht:news_item><ht:news_item_title>한은 11월 인상 전망</ht:news_item_title><ht:news_item_url>https://e.com/a</ht:news_item_url><ht:news_item_source>e</ht:news_item_source></ht:news_item></item>
<item><title>야구</title><ht:approx_traffic>5000+</ht:approx_traffic></item></channel></rss>"""


def test_gtrends_parse_and_rule_plan():
    items = gtrends.parse(RSS)
    assert items[0]["kw"] == "금리 인상" and items[0]["traffic_n"] == 20000 and items[0]["news"][0]["title"].startswith("한은")
    out = gtrends.build(items, use_ai=False)
    assert out[0]["plan"]["group"] == "경제적자유구역" and len(out[0]["plan"]["titles"]) == 3 and out[0]["plan"]["by"] == "규칙 기반"


BODY = """<!-- radar-blog -->
```json
{"action":"blog","mode":"rewrite","keyword":"금리","youtube":"https://youtu.be/abcdefghijk","channel_url":"https://www.youtube.com/@me","platforms":["wordpress","naver"]}
```
## 초안
대충 쓴 내용입니다 금리가 오르면
![p1](https://github.com/user-attachments/assets/aaa)
<img width="10" src="https://github.com/user-attachments/assets/bbb" />
"""


def test_blog_issue_parse_render(tmp_path, monkeypatch):
    cfg = blog.parse_issue(BODY)
    assert cfg["mode"] == "rewrite" and cfg["draft"].startswith("대충") and len(cfg["images"]) == 2
    assert "막 쓴 초안" in blog.make_prompt(cfg)
    post = {"title": "T", "slug": "rate-up", "intro": "I", "tags": ["a b", "c"],
            "sections": [{"h2": "S1", "paragraphs": ["p"], "image_hint": "h1"}, {"h2": "S2", "paragraphs": ["q"]}],
            "checklist": ["x"], "faq": [{"q": "q", "a": "a"}], "outro": "O", "fact_checks": ["f"]}
    monkeypatch.setattr(blog, "ai_json", lambda *a, **k: dict(post))
    d = blog.run(BODY, "9", out_root=tmp_path)
    wp = (d / "wordpress.html").read_text(encoding="utf-8")
    assert wp.count("<figure>") == 2 and "youtube.com/embed/abcdefghijk" in wp and "sub_confirmation=1" in wp
    nv = (d / "naver.txt").read_text(encoding="utf-8")
    assert "[사진 1" in nv and "#ab" in nv
    assert json.loads((d / "meta.json").read_text(encoding="utf-8"))["issue"] == "9"


def test_place_images():
    assert blog.place_images(3, ["a", "b", "c"]) == {0: ["a"], 1: ["b"], 2: ["c"]}
    assert blog.place_images(4, ["a", "b"]) == {0: ["a"], 2: ["b"]}
    assert blog.place_images(2, ["a", "b", "c"]) == {0: ["a"], 1: ["b"], 2: ["c"]}
