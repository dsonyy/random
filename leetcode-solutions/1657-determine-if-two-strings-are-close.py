from collections import defaultdict
class Solution:
    def closeStrings(self, word1: str, word2: str) -> bool:
        if len(word1) != len(word2):
            return False

        d1 = defaultdict(int)
        for ch in word1:
            d1[ch] += 1

        d2 = defaultdict(int)
        for ch in word2:
            d2[ch] += 1
        
        if sorted(d1.keys()) != sorted(d2.keys()):
            return False

        if sorted(d1.values()) != sorted(d2.values()):
            return False

        return True
        