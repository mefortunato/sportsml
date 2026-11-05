import type { TeamMapSeries } from "./types";

export type Vec3 = [number, number, number];

/** Linear interpolation between dates `floor(t)` and the next one; where
 * either is missing, the value at the nearest date that has one. */
function between<T>(
  values: (T | null)[],
  t: number,
  mix: (a: T, b: T, f: number) => T,
): T | null {
  const n = values.length;
  if (!n) return null;
  const i = Math.max(0, Math.min(n - 1, Math.floor(t)));
  const j = Math.min(n - 1, i + 1);
  const f = Math.max(0, Math.min(1, t - i));
  const [a, b] = [values[i], values[j]];
  if (a !== null && b !== null) return mix(a, b, f);
  const at = Math.max(0, Math.min(n - 1, t));
  let best: T | null = null;
  let distance = Infinity;
  values.forEach((v, k) => {
    if (v !== null && Math.abs(k - at) < distance)
      [best, distance] = [v, Math.abs(k - at)];
  });
  return best;
}

/** A team's position at a fractional date index: between two dates it
 * moves in a straight line; around a date without state it stays at the
 * nearest one that has it. */
export function positionAt(series: TeamMapSeries, t: number): Vec3 | null {
  return between(
    series.positions,
    t,
    (a, b, f) => [0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * f) as Vec3,
  );
}

/** A team's rating at a fractional date index, interpolated the same way. */
export function ratingAt(series: TeamMapSeries, t: number): number | null {
  return between(series.ratings, t, (a, b, f) => a + (b - a) * f);
}

/** Rotate around the vertical axis (yaw), then tilt toward the viewer
 * (pitch). Camera space: x right, y up, z toward the viewer. */
export function rotate([x, y, z]: Vec3, yaw: number, pitch: number): Vec3 {
  const [cy, sy] = [Math.cos(yaw), Math.sin(yaw)];
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const [cp, sp] = [Math.cos(pitch), Math.sin(pitch)];
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}

/** Perspective projection of a camera-space point: screen offsets from the
 * center (y down) and the point's size scale (1 at the center's depth). */
export function project(
  [x, y, z]: Vec3,
  size: number,
  distance = 4,
): { x: number; y: number; scale: number; depth: number } {
  const scale = distance / (distance - z);
  return { x: x * size * scale, y: -y * size * scale, scale, depth: z };
}

/** The 12 edges of the [-1, 1] cube, as pairs of corners. */
export const CUBE_EDGES: [Vec3, Vec3][] = (() => {
  const corners: Vec3[] = [];
  for (const x of [-1, 1])
    for (const y of [-1, 1]) for (const z of [-1, 1]) corners.push([x, y, z]);
  const edges: [Vec3, Vec3][] = [];
  for (let i = 0; i < corners.length; i++)
    for (let j = i + 1; j < corners.length; j++) {
      const differ = corners[i].filter((v, k) => v !== corners[j][k]).length;
      if (differ === 1) edges.push([corners[i], corners[j]]);
    }
  return edges;
})();

/** Teams ranked by rating at a date index (1 = best), skipping nulls. */
export function ranksAt(
  teams: TeamMapSeries[],
  index: number,
): Map<string, number> {
  return new Map(
    teams
      .filter((t) => t.ratings[index] !== null)
      .sort(
        (a, b) => (b.ratings[index] as number) - (a.ratings[index] as number),
      )
      .map((t, i) => [t.team.team, i + 1]),
  );
}
