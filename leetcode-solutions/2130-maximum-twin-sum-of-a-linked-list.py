# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def pairSum(self, head: Optional[ListNode]) -> int:
        t = []
        while head:
            t.append(head.val)
            head = head.next
        s = [t[i] + t[len(t)-1-i] for i in range(len(t) // 2)]
        return max(s)
        