function safeAdd(a, b) {
  const sum = a + b;
  return sum;
}
console.log(safeAdd(Number.MAX_SAFE_INTEGER, 2));
