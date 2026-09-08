# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def swapNodes(self, head: Optional[ListNode], k: int) -> Optional[ListNode]:
        a = None
        b = None
        
        node = head
        n = 1
        if n == k:
                a = node.val
        while node.next is not None:
            node = node.next
            n += 1
            if n == k:
                a = node.val

        node = head
        for i in range(n - k):
            node = node.next
        b = node.val
        node.val = a

        node = head
        for i in range(k - 1):
            node = node.next
        node.val = b

        return head
        

        
        
        