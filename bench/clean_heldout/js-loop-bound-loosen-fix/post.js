function total(xs) {
  let s = 0;
  for (let i = 0; i < xs.length; i++) {
    s += xs[i];
  }
  return s;
}

console.log(total([1, 2, 3]));
