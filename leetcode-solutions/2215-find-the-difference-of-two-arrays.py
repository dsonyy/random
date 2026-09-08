class Solution:
    def findDifference(self, nums1: List[int], nums2: List[int]) -> List[List[int]]:
        s1 = set(nums1)
        s2 = set(nums2)
        return [
            list(set(nums1[i] for i in range(len(nums1)) if nums1[i] not in s2)),
            list(set(nums2[i] for i in range(len(nums2)) if nums2[i] not in s1)),
        ]