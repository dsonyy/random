class Solution:
    def removeStars(self, s: str) -> str:
        s = [v for v in s]
        to_remove = 0
        for i in range(len(s)-1, -1, -1):
            if s[i] == "*":
                to_remove += 1
                s[i] = None
            elif to_remove > 0:
                to_remove -= 1
                s[i] = None
        r = "".join(v for v in s if v is not None)
        return r