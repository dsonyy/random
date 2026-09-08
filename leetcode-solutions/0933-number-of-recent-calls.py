class RecentCounter:
    def __init__(self):
        self.s = []

    def ping(self, t: int) -> int:
        i = 0
        for i in range(len(self.s)):
            if t-3000 <= self.s[i]:
                break
        else:
            i = len(self.s)
        self.s = self.s[i:] + [t]
        return len(self.s)


# Your RecentCounter object will be instantiated and called as such:
# obj = RecentCounter()
# param_1 = obj.ping(t)