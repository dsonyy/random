class Solution:
    def asteroidCollision(self, asteroids: List[int]) -> List[int]:
        i = 1
        while i < len(asteroids):
            if asteroids[i-1] > 0 and asteroids[i] < 0:
                if abs(asteroids[i-1]) > abs(asteroids[i]):
                    del asteroids[i]
                elif abs(asteroids[i-1]) == abs(asteroids[i]):
                    del asteroids[i-1]
                    del asteroids[i-1]
                else:
                    asteroids[i-1] = asteroids[i]
                    del asteroids[i]
                i = max(1, i-1)
            else:
                i += 1
        return asteroids