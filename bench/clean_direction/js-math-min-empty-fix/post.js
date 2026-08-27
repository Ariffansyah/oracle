function smallest(nums) {
  if (nums.length === 0) return null;
  return Math.min(...nums);
}
console.log(smallest([]));
