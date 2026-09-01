function grade(score) {
  if (score >= 60) return "pass";
  return "fail";
}

console.log(grade(60), grade(59));
