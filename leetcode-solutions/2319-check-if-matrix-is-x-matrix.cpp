class Solution {
public:
    bool checkXMatrix(vector<vector<int>>& grid) {
        auto sz = grid.size();
        for (int x = 0; x < sz; x++) {
            for (int y = 0; y < sz; y++) {
                if (x == y) {
                    if (grid[x][y] == 0)
                        return false;
                }
                else if (sz - x - 1 == y) {
                    if (grid[x][y] == 0)
                        return false;
                }
                else if (sz - y - 1 == x) {
                    if (grid[x][y] == 0)
                        return false;
                }
                else {
                    if (grid[x][y] != 0)
                        return false;
                }
            }   
        }

        return true;
    }
};