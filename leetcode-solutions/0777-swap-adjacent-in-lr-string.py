class Solution:
    def canTransform(self, start: str, result: str) -> bool:
        if [v for v in start if v != "X"] != [v for v in result if v != "X"]:
            return False

        i, j = 0, 0
        while i < len(start):
            print(i, j)
            if start[i] == "L":
                j += result[j:].index("L")
                if j > i:
                    return False
                j += 1
            elif start[i] == "R":
                j += result[j:].index("R")
                if i > j:
                    return False
                j += 1
            i += 1

        return True





        