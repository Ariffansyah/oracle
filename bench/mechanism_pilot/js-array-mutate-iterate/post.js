function removeEvens(items) {
  for (const x of items) {
    if (x % 2 === 0) items.splice(items.indexOf(x), 1);
  }
  return items;
}
console.log(removeEvens([2, 4, 6, 8, 1, 3]));
