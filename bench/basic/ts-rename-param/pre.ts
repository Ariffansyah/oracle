interface Point { x: number; y: number; }

function dist(p: Point): number {
  return Math.abs(p.x) + Math.abs(p.y);
}

console.log(dist({ x: -3, y: 4 }));
