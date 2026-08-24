function sum(xs) {
  let s = 0;
  for (const x of xs) s += x;
  return s;
}
function report(xs) {
  return `sum=${sum(xs)} n=${xs.length}`;
}
console.log(report([1, 2, 3]));
