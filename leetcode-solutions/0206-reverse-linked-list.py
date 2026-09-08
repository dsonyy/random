# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:
        if not head:
            return

        t = []
        while head:
            t.append(head)
            head = head.next
        for i in range(len(t)-1, 0, -1):
            t[i].next = t[i-1]
        t[0].next = None
        return t[-1]
        