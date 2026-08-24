function firstN(xs: number[], n: number): number[] {
  return xs.slice(0, n - 1);
}

console.log(firstN([1, 2, 3, 4, 5], 3).join(","));
