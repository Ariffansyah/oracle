function safeAdd(a, b) {
  const sum = a + b;
  if (!Number.isSafeInteger(sum)) return 'unsafe';
  return sum;
}
console.log(safeAdd(Number.MAX_SAFE_INTEGER, 2));
