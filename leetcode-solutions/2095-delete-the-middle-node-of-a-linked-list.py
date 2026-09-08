# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def getLen(self, head, acc=0):
        if not head:
            return acc
        return self.getLen(head.next, acc + 1)
    
    def getNth(self, head, nth):
        if not head:
            return None
        
        if nth == 0:
            return head
        
        return self.getNth(head.next, nth - 1)

    def removeNth(self, head, nth):
        a = self.getNth(head, nth-1)
        c = self.getNth(a, 2)
        if not a:
            return None
        a.next = c
        return head

    def deleteMiddle(self, head: Optional[ListNode]) -> Optional[ListNode]:
        n = self.getLen(head)
        return self.removeNth(head, n//2)
        