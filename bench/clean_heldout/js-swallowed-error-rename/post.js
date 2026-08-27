function parseConfig_x(text) {
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error("bad config");
  }
}
try {
  console.log(parseConfig_x("{oops"));
} catch (e) {
  console.log("caught:", e.message);
}
