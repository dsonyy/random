class Solution:
    def maxOperations(self, nums: List[int], k: int) -> int:
        nums.sort()
        l, r = 0, len(nums) - 1
        result = 0
        while l < r:
            v = nums[l] + nums[r]
            if v == k:
                result += 1
                l += 1
                r -= 1
            elif v > k:
                r -= 1
            else:
                l += 1
        return result
        