class Solution:
    def canMakeArithmeticProgression(self, arr: List[int]) -> bool:
        x = sorted(arr)
        d = x[1] - x[0]
        for a,b in zip(x, x[1:]):
            if b-a != d:
                return False
        return True
        