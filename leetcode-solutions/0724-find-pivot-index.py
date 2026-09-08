class Solution:
    def pivotIndex(self, nums: List[int]) -> int:
        left = [sum(nums[:i]) for i in range(len(nums))]
        right = [sum(nums[i+1:]) for i in range(len(nums))]
        for i in range(len(nums)):
            if left[i] == right[i]:
                return i
        return -1