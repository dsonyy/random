class Solution {
public:
    bool divisorGame(int N) {
        bool dp[N];
        dp[0] = false;
        
        for (int i = 2; i <= N; i++) {
            dp[i - 1] = false;
            for (int j = 1; j < i; j++) {
                if (i % j == 0 && !dp[i - j - 1]) {
                    dp[i - 1] = true;
                    break;
                }
            }   
        }
        return dp[N - 1];
    }
};