class Solution {
public:
    int minPathSum(vector<vector<int>>& grid) {
        for (int y = 1; y < grid.size(); y++) {
            grid[y][0] += grid[y - 1][0];
        }
        
        for (int x = 1; x < grid[0].size(); x++) {
            grid[0][x] += grid[0][x - 1];
        }
        
        for (int y = 1; y < grid.size(); y++) {
            for (int x = 1; x < grid[0].size(); x++) {
                if (grid[y - 1][x] > grid[y][x - 1]) grid[y][x] += grid[y][x - 1];
                else grid[y][x] += grid[y - 1][x];
            }
            
        }
        return grid[grid.size() - 1][grid[0].size() - 1];
    }
};