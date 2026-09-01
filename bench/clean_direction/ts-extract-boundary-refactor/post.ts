function passing(score: number): boolean {
  return score >= 60;
}

function grade(score: number): string {
  if (passing(score)) return "pass";
  return "fail";
}

console.log(grade(60), grade(59));
