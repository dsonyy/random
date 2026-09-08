class Solution:
    def equalPairs(self, grid: List[List[int]]) -> int:
        n = len(grid)
        cnt = 0
        for row in grid:
            for i in range(n):
                col = [grid[j][i] for j in range(n)]

                if row == col:
                    cnt += 1
        return cnt

        