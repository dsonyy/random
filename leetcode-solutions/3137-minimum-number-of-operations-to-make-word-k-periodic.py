from collections import defaultdict

class Solution:
    def minimumOperationsToMakeKPeriodic(self, word: str, k: int) -> int:
        n = len(word)
        m = defaultdict(int)
        for i in range(k, n+1, k):
            m[word[i-k:i]] += 1
        total = sum(m.values())
        good = max(m.values())
        swaps = total - good
        return swaps

        