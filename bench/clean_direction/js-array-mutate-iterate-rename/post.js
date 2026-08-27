function removeEvens(items_x) {
  const copy = [...items_x];
  for (const x of copy) {
    if (x % 2 === 0) items_x.splice(items_x.indexOf(x), 1);
  }
  return items_x;
}
console.log(removeEvens([2, 4, 6, 8, 1, 3]));
