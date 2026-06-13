# Test file for math_app.py

def test_standard_deviation():
    from math_app import standard_deviation
    assert standard_deviation([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0
