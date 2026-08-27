function withTag(items) {
  const out = [...items];
  out.push("tagged");
  return out;
}
const data_x = [1, 2, 3];
const result = withTag(data_x);
console.log(data_x, result);
