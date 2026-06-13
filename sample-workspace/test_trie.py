# test_trie.py

import unittest
from trie import Trie

class TestTrie(unittest.TestCase):
    def setUp(self):
        self.trie = Trie()

    def test_insert(self):
        self.trie.insert('apple')
        self.assertTrue(self.trie.search('apple'))

    def test_search_prefix(self):
        self.trie.insert('apples')
        self.assertTrue(self.trie.startsWith('app'))

    def test_not_found(self):
        self.assertFalse(self.trie.search('banana'))

if __name__ == '__main__':
    unittest.main()