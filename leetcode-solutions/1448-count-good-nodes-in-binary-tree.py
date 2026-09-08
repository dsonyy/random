# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
class Solution:
    def goodNodes(self, root: TreeNode) -> int:
        def fn(root) -> int:
            cnt = 0
            if root.left:
                if root.left.val >= root.val:
                    cnt += 1
                else:
                    root.left.val = root.val
                cnt += fn(root.left)

            if root.right:
                if root.right.val >= root.val:
                    cnt += 1
                else:
                    root.right.val = root.val
                cnt += fn(root.right)
            
            return cnt
        
        return fn(root) + 1

        