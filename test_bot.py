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
from main import classify_request

assert classify_request('650 libras 8720 pies') == 'bw'
assert classify_request('650 pounds 8720 feet') == 'bw'
assert classify_request('FT 5.71 620') == 'ft'
assert classify_request('BW 5.71 weight 620') == 'ft'
assert classify_request('current weight 7.25 speed 150 target 6.3') == 'swrap'
assert classify_request('peso actual 7.25 velocidad 150 objetivo 6.3') == 'swrap'
assert classify_request('620 8550') == 'bw'
print('Intent tests passed.')
