function scale(values, factor) {
  return values.map((v) => v * factor);
}

console.log(scale([1, 2, 3], 2).join(","));
