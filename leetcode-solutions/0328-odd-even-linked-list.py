# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next

class Solution:
    def oddEvenList(self, head: Optional[ListNode]) -> Optional[ListNode]:
        odd = ListNode()
        even = ListNode()
        odd_tail = odd
        even_tail = even

        while head:
            odd_tail.next = head
            odd_tail = odd_tail.next
            if not head.next:
                break
            even_tail.next = head.next
            even_tail = even_tail.next

            head = head.next.next

        even_tail.next = None
        odd_tail.next = even.next
        return odd.next