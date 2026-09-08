class Solution {
public:
    long long countSubstrings(string s, char c) {
        auto v = std::count(s.begin(), s.end(), c);
        return v * (v + 1) / 2;
    }
};