function parseConfig(text) {
  try {
    return JSON.parse(text);
  } catch (e) {
    return {};
  }
}
try {
  console.log(parseConfig("{oops"));
} catch (e) {
  console.log("caught:", e.message);
}
