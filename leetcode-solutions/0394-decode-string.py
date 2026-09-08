class Solution:
    def decodeString(self, s: str) -> str:
        result = ""

        l = 0
        for i in range(len(s)):
            if s[i] == "[":
                break
            elif not s[i].isnumeric():
                result += s[i]
                l = i+1
        else:
            return s

        k = int(s[l:i])
        
        depth = 1
        for j in range(i+1, len(s)):
            if s[j] == "[":
                depth += 1
            elif s[j] == "]":
                depth -= 1
            
            if depth == 0:
                result += k * self.decodeString(s[i+1:j])
                break
        
        if s[j+1:]:
            result += self.decodeString(s[j+1:])

        return result
        