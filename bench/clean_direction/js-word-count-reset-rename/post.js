function lineWordCounts_x(lines) {
  const out = [];
  for (const line of lines) {
    let count = 0;
    for (const w of line.split(" ")) count++;
    out.push(count);
  }
  return out;
}
console.log(lineWordCounts_x(["a b", "c d e", "f"]));
