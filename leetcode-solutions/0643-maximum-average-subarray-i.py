class Solution:
    def findMaxAverage(self, nums: List[int], k: int) -> float:
        s = sum(nums[:k])
        best_s = s
        for i in range(k, len(nums)):
            s = s - nums[i-k] + nums[i]
            best_s = max(best_s, s)
        return best_s / k

        