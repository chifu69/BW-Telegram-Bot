import math
from main import calculate_bw, calculate_ft, calculate_swrap


def test_bw_and_ft_are_reversible():
    bw = calculate_bw(620, 8550, 48)
    feet = calculate_ft(bw, 620, 48)
    assert math.isclose(feet, 8550, rel_tol=1e-10)


def test_swrap_example():
    result = calculate_swrap(7.25, 150, 6.3)
    assert math.isclose(result, 172.61904761904762, rel_tol=1e-12)
