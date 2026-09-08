class Solution:
    def increasingTriplet(self, nums: List[int]) -> bool:
        i = float("inf")
        j = None
        for idx, x in enumerate(nums):
            if j is not None and i < x and j < x:
                return True
            elif i < x:
                j = x
            else:
                i = x
        return False