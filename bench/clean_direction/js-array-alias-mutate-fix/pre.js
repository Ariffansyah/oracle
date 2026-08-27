function withTag(items) {
  const out = items;
  out.push("tagged");
  return out;
}
const data = [1, 2, 3];
const result = withTag(data);
console.log(data, result);
