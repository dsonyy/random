# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next


def _len(self: ListNode, i=1) -> int:
    if self.next is None:
        return i
    return i + _len(self.next)

class Solution:
    def addTwoNumbers(self, l1: Optional[ListNode], l2: Optional[ListNode]) -> Optional[ListNode]:
        s = 0

        e0, e1 = l1, l2
        carry = 0
        root = None
        for i in range(max(_len(l1), _len(l2))):
            if i == 0:
                root = ListNode()
                result = root
            else:
                result.next = ListNode()
                result = result.next

            v0 = 0 if e0 is None else e0.val
            v1 = 0 if e1 is None else e1.val
            
            v = (v0 + v1 + carry) % 10
            carry = (v0 + v1 + carry) // 10

            result.val = v

            e0 = None if e0 is None else e0.next
            e1 = None if e1 is None else e1.next

        if carry > 0:
            result.next = ListNode(carry)

        return root
        
        