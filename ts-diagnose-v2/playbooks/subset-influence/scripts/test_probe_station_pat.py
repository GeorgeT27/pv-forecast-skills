import probe_logs

def test_pattern_from_config_aliases():
    cfg = {"test_station": "baimahu", "test_station_aliases": ["白马湖", "bmh"]}
    pat = probe_logs.station_pattern(cfg)
    assert pat.search("epoch 3 白马湖 rmse=0.123")
    assert pat.search("BAIMAHU eval rmse")
    assert pat.search("[bmh] chunk2 rmse 0.2")
    assert not pat.search("yalong eval rmse")

def test_pattern_fallback_when_config_empty():
    pat = probe_logs.station_pattern({})
    assert pat is probe_logs.DEFAULT_STATION_PAT

def test_alias_regex_escaped():
    pat = probe_logs.station_pattern({"test_station": "st.1", "test_station_aliases": []})
    assert pat.search("st.1 rmse") and not pat.search("stX1 rmse")
