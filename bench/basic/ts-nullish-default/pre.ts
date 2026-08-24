function label(name: string | null): string {
  return name ?? "anon";
}

console.log(JSON.stringify(label("")));
