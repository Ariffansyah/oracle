function safeDivide(a, b_x) {
  if (b_x === 0) return null;
  return a / b_x;
}
console.log(safeDivide(10, 0));
