class Solution:
    def findTheLongestBalancedSubstring(self, s: str) -> int:
        best = 0
        zeros = 0
        ones = 0
        for v in s:
            if v == "0" and ones == 0: 
                zeros += 1
            elif v == "0" and ones > 0:
                best = max(best, min(zeros, ones))
                ones = 0
                zeros = 1
            elif v == "1":
                ones += 1
        best = max(best, min(zeros, ones))
        return 2 * best


        