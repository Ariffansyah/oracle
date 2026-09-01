function passing(score) {
  return score >= 60;
}

function grade(score) {
  if (passing(score)) return "pass";
  return "fail";
}

console.log(grade(60), grade(59));
