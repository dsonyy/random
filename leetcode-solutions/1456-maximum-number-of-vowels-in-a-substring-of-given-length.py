class Solution:
    def maxVowels(self, s: str, k: int) -> int:
        count = sum(1 for ch in s[:k] if ch in "aeiou")
        best = count
        for i in range(k, len(s)):
            if s[i-k] in "aeiou":
                count -= 1
            if s[i] in "aeiou":
                count += 1
            best = max(best, count)
        return best