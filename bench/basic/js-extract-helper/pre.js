function report(xs) {
  let s = 0;
  for (const x of xs) s += x;
  return `sum=${s} n=${xs.length}`;
}
console.log(report([1, 2, 3]));
