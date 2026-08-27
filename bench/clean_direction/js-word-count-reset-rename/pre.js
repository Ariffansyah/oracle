function lineWordCounts(lines) {
  const out = [];
  for (const line of lines) {
    let count = 0;
    for (const w of line.split(" ")) count++;
    out.push(count);
  }
  return out;
}
console.log(lineWordCounts(["a b", "c d e", "f"]));
