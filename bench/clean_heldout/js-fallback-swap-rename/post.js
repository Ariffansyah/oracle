function label_x(name, fallback) {
  return name || fallback;
}
console.log(label_x("", "anonymous"), label_x("ada", "anonymous"));
