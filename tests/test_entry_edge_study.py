import pandas as pd

from src.entry_edge_study import build_events, episode_mask


def test_episode_mask_declusters_within_20_sessions():
    assert episode_mask(pd.Series(["1", "1", "1", "2"]).to_numpy(),
                        pd.Series([10, 20, 31, 1]).to_numpy()).tolist() == [True, False, True, True]


def test_build_events_uses_next_open_and_matched_0050_dates():
    dates = pd.date_range("2022-01-03", periods=22, freq="B")
    stock = pd.DataFrame({"stock_id":"1234", "date":dates, "open":100., "high":110.,
                          "low":109., "close":110., "limit_up":110., "locked":True,
                          "prior10_locked":2., "within_pos":range(22), "group_size":22})
    bench = pd.DataFrame({"stock_id":"0050", "date":dates, "open":100., "high":100.,
                          "low":100., "close":100., "limit_up":110., "locked":False,
                          "prior10_locked":0., "within_pos":range(22), "group_size":22})
    events = build_events(pd.concat([bench, stock], ignore_index=True))
    row = events[(events.signal == "A_NEAR_LIMIT") & (events.dataset == "Raw") &
                 (events.signal_date == dates[0]) & (events.horizon == 5)].iloc[0]
    assert row.entry_date == dates[1]
    assert row.exit_date == dates[5]
    assert row.benchmark_return == 0
