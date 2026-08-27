function label(name, fallback) {
  return name || fallback;
}
console.log(label("", "anonymous"), label("ada", "anonymous"));
