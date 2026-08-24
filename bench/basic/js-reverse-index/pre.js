function total(arr) {
  let s = 0;
  for (let i = arr.length - 1; i >= 0; i--) s += arr[i];
  return s;
}
console.log(total([1, 2, 3, 4]));
