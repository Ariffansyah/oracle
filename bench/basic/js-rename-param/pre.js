function scale(xs, k) {
  return xs.map((x) => x * k);
}

console.log(scale([1, 2, 3], 2).join(","));
