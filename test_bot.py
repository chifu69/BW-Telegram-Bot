from main import (
    calculate_bw,
    calculate_ft,
    calculate_swrap,
    normalize_spoken_numbers,
)


def close(a, b, tolerance=0.02):
    return abs(a - b) <= tolerance


assert close(calculate_bw(620, 8550, 48), 5.71)
assert close(calculate_ft(5.71, 620, 48), 8550, 20)
assert close(calculate_swrap(7.25, 150, 6.3), 172.62)
assert "620" in normalize_spoken_numbers("six hundred twenty pounds", "en")
assert "8550" in normalize_spoken_numbers("eight thousand five hundred fifty feet", "en")
assert "620" in normalize_spoken_numbers("seiscientos veinte libras", "es")
assert "8550" in normalize_spoken_numbers("ocho mil quinientos cincuenta pies", "es")
assert "7.25" in normalize_spoken_numbers("seven point two five", "en")
assert "7.25" in normalize_spoken_numbers("siete punto dos cinco", "es")
print("All V2 tests passed.")
