import pytest

from experiment_power import sample_size_per_arm, sensitivity_table


def test_sample_size_sensitivity_matches_documented_approximation():
    assert sample_size_per_arm(212 / 631, 0.10) == 3021
    assert sample_size_per_arm(212 / 631, 0.15) == 1323
    assert sample_size_per_arm(212 / 631, 0.20) == 733
    assert sample_size_per_arm(212 / 631, 0.25) == 461


def test_sensitivity_table_uses_flagged_volume_and_baseline():
    rows = sensitivity_table()
    assert len(rows) == 4
    assert rows[0]["eligible_per_month"] == 667
    assert rows[0]["months"] == pytest.approx(6042 / 666.6, rel=0.01)


@pytest.mark.parametrize("rate,reduction", [(0, .2), (1, .2), (.3, 0), (.3, 1), (.3, -0.1)])
def test_sample_size_rejects_invalid_rates(rate, reduction):
    with pytest.raises(ValueError):
        sample_size_per_arm(rate, reduction)
