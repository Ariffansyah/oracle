function lineWordCounts(lines) {
  const out = [];
  let count = 0;
  for (const line of lines) {
    for (const w of line.split(" ")) count++;
    out.push(count);
  }
  return out;
}
console.log(lineWordCounts(["a b", "c d e", "f"]));
