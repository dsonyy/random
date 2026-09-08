class Solution:
    def compress(self, chars: List[str]) -> int:
        ch = chars[0]
        n = 1
        j = 0
        for i in range(1, len(chars)):
            if chars[i] == ch:
                n += 1
            elif chars[i] != ch and n == 1:
                chars[j] = ch
                ch = chars[i]
                n = 1
                j += 1
            elif chars[i] != ch and n > 1:
                chars[j] = ch
                for c in str(n):
                    j += 1
                    chars[j] = c 
                ch = chars[i]
                n = 1
                j += 1
        
        if n == 1:
            chars[j] = ch
            j += 1
        elif n > 1:
            chars[j] = ch
            for c in str(n):
                j += 1
                chars[j] = c 
            j += 1
        return j
            
            
        