class Solution:
    def longestOnes(self, nums: List[int], k: int) -> int:
        l,r = 0, 0
        best = 0
        ones = 0
        ks = k
        while l < len(nums) and r < len(nums):
            print(l,r,ones,ks, best)
            if nums[r] == 1:
                ones += 1
                r += 1
            elif nums[r] == 0:
                if ks > 0:
                    ks -= 1
                    r += 1
                elif ks == 0:
                    if nums[l] == 0:
                        ks += 1
                    l += 1
            best = max(best, r - l)
        return best