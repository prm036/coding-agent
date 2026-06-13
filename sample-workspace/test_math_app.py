def test_standard_deviation():
    numbers = [1, 2, 3, 4, 5]
    result = standard_deviation(numbers)
    assert abs(result - 1.4142135623730951) < 1e-9
