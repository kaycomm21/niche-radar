from radar.mychannel import rows_to_dicts, summarize


def test_rows_and_rpm():
    resp = {"columnHeaders": [{"name": "video"}, {"name": "views"}, {"name": "estimatedRevenue"}], "rows": [["a", 1000, 3.0], ["b", 500, 1.0]]}
    vids = rows_to_dicts(resp)
    assert vids[0] == {"video": "a", "views": 1000, "estimatedRevenue": 3.0}
    s = summarize("경제적자유구역", {"views": 1500, "estimatedRevenue": 4500.0}, vids)
    assert s["rpm"] == 3000.0 and s["median_video_views"] == 1000
    assert summarize("x", {"views": 100}, [])["rpm"] is None     # 수익화 전
