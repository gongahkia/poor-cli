def two_sum(nums, target):
    """
    Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.

    You may assume that each input would have exactly one solution, and you may not use the same element twice.

    You can return the answer in any order.
    """
    num_map = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in num_map:
            return [num_map[complement], i]
        num_map[num] = i
    return []

if __name__ == "__main__":
    # Test cases
    nums1 = [2, 7, 11, 15]
    target1 = 9
    print(f"Input: nums = {nums1}, target = {target1}")
    print(f"Output: {two_sum(nums1, target1)}") # Expected: [0, 1] or [1, 0]

    nums2 = [3, 2, 4]
    target2 = 6
    print(f"Input: nums = {nums2}, target = {target2}")
    print(f"Output: {two_sum(nums2, target2)}") # Expected: [1, 2] or [2, 1]

    nums3 = [3, 3]
    target3 = 6
    print(f"Input: nums = {nums3}, target = {target3}")
    print(f"Output: {two_sum(nums3, target3)}") # Expected: [0, 1] or [1, 0]

    nums4 = [1, 5, 9, 13]
    target4 = 10
    print(f"Input: nums = {nums4}, target = {target4}")
    print(f"Output: {two_sum(nums4, target4)}") # Expected: [0, 2] or [2, 0]
