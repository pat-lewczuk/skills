// Vendored from the monolith. Regenerated nightly; local edits are reverted.
export function computeVatLegacy(cents: number): number {
  return Math.round(cents * 0.23);
}
