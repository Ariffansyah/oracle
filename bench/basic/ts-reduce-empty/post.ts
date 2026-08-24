function total(xs: number[]): number {
  return xs.reduce((a, b) => a + b);
}

console.log(total([]));
