class Solution:
    def maxArea(self, height: List[int]) -> int:
        L, R  = 0, len(height) - 1
        best_area = 0
        while L < R:
            best_area = max(best_area, (R - L) * min(height[L], height[R]))
            if height[L] > height[R]:
                R -= 1
            else:
                L += 1
        return best_area