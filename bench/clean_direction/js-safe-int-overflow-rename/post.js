function safeAdd(a, b) {
  const sum_x = a + b;
  if (!Number.isSafeInteger(sum_x)) return 'unsafe';
  return sum_x;
}
console.log(safeAdd(Number.MAX_SAFE_INTEGER, 2));
