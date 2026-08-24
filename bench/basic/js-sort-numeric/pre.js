function sorted(xs) {
  return [...xs].sort((a, b) => a - b);
}
console.log(sorted([10, 9, 1, 20]).join(","));
