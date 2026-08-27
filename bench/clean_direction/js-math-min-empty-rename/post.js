function smallest(nums_x) {
  if (nums_x.length === 0) return null;
  return Math.min(...nums_x);
}
console.log(smallest([]));
