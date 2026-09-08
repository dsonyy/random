class Solution:
    def checkPalindrome(self, s: str, center: int, size, ) -> str:
        pass

    def longestPalindrome(self, s: str) -> str:

        n = len(s)

        if len(s) == 1:
            return s

        best = s[0]

        for i in range(n):
            sz = 1
            l, r = i, i
            while l - 1 >= 0 and r + 1 < n and s[l - 1] == s[r + 1]:
                sz += 2
                l -= 1
                r += 1
            if sz > len(best):
                best = s[l:r+1]

        for i in range(1, n):
            if s[i] != s[i-1]: continue
            sz = 2
            l, r = i-1, i
            while l - 1 >= 0 and r + 1 < n and s[l - 1] == s[r + 1]:
                sz += 2
                l -= 1
                r += 1
            if sz > len(best):
                best = s[l:r+1]


        
        return best