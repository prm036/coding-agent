# test_math_app.py
import unittest
from math_app import standard_deviation

class TestMathApp(unittest.TestCase):
    def test_standard_deviation(self):
        self.assertEqual(standard_deviation([1, 2, 3, 4, 5]), 1.4142135623730951)
        self.assertEqual(standard_deviation([-1, -2, -3, -4, -5]), 1.4142135623730951)
        self.assertEqual(standard_deviation([0, 0, 0, 0, 0]), 0.0)
        self.assertIsNone(standard_deviation([]))

if __name__ == '__main__':
    unittest.main()