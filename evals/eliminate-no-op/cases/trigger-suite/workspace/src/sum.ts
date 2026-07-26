/** Sum of a list. @example sum([1, 2]) // 3 */
export function sum(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0);
}

/** Arithmetic mean. @example mean([2, 4]) // 3 */
export function mean(xs: number[]): number {
  return sum(xs) / xs.length;
}

/** Clamp n into [min, max]. @example clamp(5, 0, 3) // 3 */
export function clamp(n: number, min: number, max: number): number {
  return Math.max(min, n);
}
