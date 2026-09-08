class Solution:
    def canJump(self, nums: List[int]) -> bool:
        n = len(nums)
        reachable = [False] * n
        reachable[0] = True

        for i in range(n):
            if not reachable[i]:
                continue

            for j in range(i+1, i+1+nums[i]):
                if j >= n:
                    break
                reachable[j] = True
        
        return reachable[-1]