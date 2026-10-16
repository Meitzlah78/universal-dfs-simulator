from nfl_scoring import apply_two_point_conversion


def test_passing_conversion_credits_passer_and_receiver_two_each():
    scores = {"QB": 10.0, "WR": 7.0}
    apply_two_point_conversion(scores, passer="QB", receiver="WR")
    assert scores == {"QB": 12.0, "WR": 9.0}


def test_rushing_conversion_credits_rusher_two():
    scores = {"RB": 8.5}
    apply_two_point_conversion(scores, rusher="RB")
    assert scores == {"RB": 10.5}


def test_failed_conversion_scores_zero():
    scores = {"QB": 10.0, "WR": 7.0, "RB": 8.5}
    before = scores.copy()
    apply_two_point_conversion(
        scores,
        passer="QB",
        receiver="WR",
        rusher="RB",
        successful=False,
    )
    assert scores == before


def test_passing_conversion_does_not_also_credit_rusher():
    scores = {}
    apply_two_point_conversion(
        scores,
        passer="Emergency Passer",
        receiver="QB Receiver",
        rusher="RB",
    )
    assert scores == {"Emergency Passer": 2.0, "QB Receiver": 2.0}
