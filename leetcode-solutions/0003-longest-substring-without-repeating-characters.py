class Solution:
    def lengthOfLongestSubstring(self, s: str) -> int:
        if len(s) == 0:
            return 0
        
        if len(s) == 1:
            return 1

        start, end = 0,1
        best = s[start]
        chars = {s[start]}
        while end < len(s):
            if s[end] in chars and start <= end:
                chars.remove(s[start])
                start += 1
            else:
                chars.add(s[end])
                end += 1
                if len(s[start:end]) > len(best):
                    best = s[start:end]
        
        return len(best)
 

        