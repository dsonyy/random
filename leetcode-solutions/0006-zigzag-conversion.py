class Solution:
    def convert(self, s: str, numRows: int) -> str:
        tab = []
        i = 0
        while i < len(s):
            tab.append([])
            for row in range(numRows):
                ch = s[i:i+1]
                tab[-1].append(ch)
                i += 1

            for rrow in range(numRows - 2, 0, -1):
                ch = s[i:i+1]
                tab.append([("" if rrow != v else ch) for v in range(numRows)])
                i += 1

        return "".join([tab[j][i] for i in range(numRows) for j in range(len(tab))])
            