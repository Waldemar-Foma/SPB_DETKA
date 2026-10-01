from backend.services import scoring_config as cfg


def test_balanced_weights_sum_to_one():
    weights = cfg.get_weights('balanced')
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    for key in ['product', 'okpd2', 'experience', 'win_rate', 'customer', 'geography', 'reviews', 'workload']:
        assert key in weights


def test_semantic_and_geography_have_meaningful_weight():
    weights = cfg.get_weights('balanced')
    assert weights['product'] >= 0.25
    assert weights['geography'] >= 0.10
