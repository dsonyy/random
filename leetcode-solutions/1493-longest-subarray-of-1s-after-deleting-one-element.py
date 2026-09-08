class Solution:
    def longestSubarray(self, nums: List[int]) -> int:
        l, r = 0, 0
        zero_i = None
        best = 0
        while r < len(nums):
            if nums[r] == 1:
                r += 1
            elif nums[r] == 0 and zero_i is None:
                zero_i = r
                r += 1
            elif nums[r] == 0 and zero_i is not None:
                l = zero_i + 1
                zero_i = r
                r += 1
            best = max(best, r - l - (0 if zero_i is None else 1))

        if best == len(nums):
            return best - 1

        return best
                
                
