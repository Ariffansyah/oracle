function parseConfig(text) {
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error("bad config");
  }
}
try {
  console.log(parseConfig("{oops"));
} catch (e) {
  console.log("caught:", e.message);
}
