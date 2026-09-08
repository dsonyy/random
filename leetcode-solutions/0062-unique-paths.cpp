class Solution {
public:
    int uniquePaths(int m, int n) {
        int dp[n][m];
        
        for (int y = 0; y < n; y++) {
            dp[y][0] = 1;
        }
        
        for (int x = 0; x < m; x++) {
            dp[0][x] = 1;
        }
        
        for (int y = 1; y < n; y++) {
            for (int x = 1; x < m; x++) {
                dp[y][x] = dp[y - 1][x] + dp[y][x - 1];
            }
        }
        return dp[n - 1][m - 1];
    }
};