# test_trie.py

import unittest
from trie import Trie

class TestTrie(unittest.TestCase):
    def setUp(self):
        self.trie = Trie()

    def test_insert(self):
        self.trie.insert('apple')
        self.assertTrue(self.trie.search('apple'))

    def test_search(self):
        self.trie.insert('banana')
        self.assertTrue(self.trie.search('banana'))
        self.assertFalse(self.trie.search('apples'))

    def test_startsWith(self):
        self.trie.insert('cherry')
        self.assertTrue(self.trie.startsWith('che'))
        self.assertFalse(self.trie.startsWith('cherries'))

if __name__ == '__main__':
    unittest.main()