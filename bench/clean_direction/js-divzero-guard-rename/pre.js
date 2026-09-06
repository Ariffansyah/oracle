function safeDivide(a, b) {
  if (b === 0) return null;
  return a / b;
}
console.log(safeDivide(10, 0));
