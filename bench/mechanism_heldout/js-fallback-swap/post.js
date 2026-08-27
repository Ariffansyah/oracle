function label(name, fallback) {
  return fallback || name;
}
console.log(label("", "anonymous"), label("ada", "anonymous"));
