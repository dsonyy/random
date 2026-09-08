class Solution {
public:
    int maxProfit(vector<int>& prices) {
        int sell = 0;
        int buy = INT_MAX;
        for (int i = 0; i < prices.size(); i++) {
            if (buy > prices[i]) buy = prices[i];
            else if (sell < prices[i] - buy) sell = prices[i] - buy;
        }
        return sell;
    }
};