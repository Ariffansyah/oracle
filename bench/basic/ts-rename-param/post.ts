interface Point { x: number; y: number; }

function dist(pt: Point): number {
  return Math.abs(pt.x) + Math.abs(pt.y);
}

console.log(dist({ x: -3, y: 4 }));
