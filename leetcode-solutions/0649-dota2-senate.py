class Solution:
    def predictPartyVictory(self, senate: str) -> str:
        banned = [False] * len(senate)
        
        r_count = 0
        d_count = 0
        for i in range(len(senate)):
            if senate[i] == "R": 
                r_count += 1
            elif senate[i] == "D":
                d_count += 1

        r = 0
        d = 0
        while r_count > 0 and d_count > 0:
            for i in range(len(senate)):
                if banned[i]:
                    continue
                elif senate[i] == "R" and d > 0: 
                    banned[i] = True
                    r_count -= 1
                    d -= 1
                elif senate[i] == "D" and r > 0:
                    banned[i] = True
                    d_count -= 1
                    r -= 1
                elif senate[i] == "R": 
                    r += 1
                elif senate[i] == "D":
                    d += 1
        
        if r_count > 0: return "Radiant"
        else: return "Dire"

