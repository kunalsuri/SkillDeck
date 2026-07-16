// Formats a raw token_estimate into the compact chip label used across the
// catalog and skill detail pages. Keep in parity with the chars/4 estimate
// documented in kitchen/nutrition.py - this file only formats, it never
// recomputes the estimate.
export function formatTokens(n: number): string {
  if (n < 1000) {
    return `~${n} tokens`;
  }
  if (n < 10000) {
    return `~${(n / 1000).toFixed(1)}k tokens`;
  }
  return `~${Math.round(n / 1000)}k tokens`;
}

export type CostBucket = 'light' | 'moderate' | 'heavy';

export function costBucket(n: number): CostBucket {
  if (n < 500) return 'light';
  if (n <= 2000) return 'moderate';
  return 'heavy';
}
