class Solution:
    def isMonotonic(self, nums: List[int]) -> bool:
        if len(nums) < 2:
            return True
        elif nums[0] == nums[1]:
            return self.isMonotonic(nums[1:])
        elif nums[0] < nums[1]:
            for i, j in zip(nums[1:], nums[2:]):
                if i > j:
                    return False
        else:
            for i, j in zip(nums[1:], nums[2:]):
                if i < j:
                    return False
        return True
        