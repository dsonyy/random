class Solution:
    def reverseVowels(self, s: str) -> str:
        vovels = ["a","e","i","o","u", "A", "E", "I", "O", "U"]
        vv = [v for v in s if v in vovels]
        ww = [(None if v in vovels else v) for v in s]

        idx = len(vv) - 1
        for i in range(len(ww)):
            if ww[i] is None:
                ww[i] = vv[idx]
                idx -= 1
        
        return "".join(ww)

        