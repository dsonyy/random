class Solution:
    def kidsWithCandies(self, candies: List[int], extraCandies: int) -> List[bool]:
        m = max(candies)
        return [extraCandies + candies[i] >= m for i in range(len(candies))]
        