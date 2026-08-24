function makeGetters() {
  const out = [];
  for (let i = 0; i < 3; i++) {
    out.push(() => i);
  }
  return out;
}

console.log(makeGetters().map((f) => f()).join(","));
