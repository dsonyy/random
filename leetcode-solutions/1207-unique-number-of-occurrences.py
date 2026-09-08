from collections import defaultdict
class Solution:
    def uniqueOccurrences(self, arr: List[int]) -> bool:
        d = defaultdict(int)
        for v in arr:
            d[v] += 1
        
        values = d.values()
        return len(values) == len(list(set(values))) 
        