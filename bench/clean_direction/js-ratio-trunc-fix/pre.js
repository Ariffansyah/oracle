function scorePercentage(correct, total) {
  return Math.trunc(correct / total) * 100.0;
}
console.log(scorePercentage(1, 3).toFixed(2));
