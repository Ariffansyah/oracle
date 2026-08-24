function sorted(xs: number[]): number[] {
  return [...xs].sort((a, b) => a - b);
}

const data = [3, 1, 2];
sorted(data);
console.log(data.join(","));
