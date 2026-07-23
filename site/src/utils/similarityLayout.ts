// Pure layout/scoring math for the Similarity Galaxy (SimilarityGalaxy.tsx).
// Kept dependency-free and framework-free so it's directly testable and so
// the component itself never needs a physics/graph-layout library - the
// "magnet" effect is one interpolation formula applied on every render.
export interface Point {
  x: number;
  y: number;
}

// Deterministic scattered "home" position for neighbor index i of n, in a
// 0-100 percentage coordinate space centered on (50, 50). Evenly spaced by
// angle around a wide radius so dragging the anchor toward a node visibly
// pulls high-score neighbors in from the edge; alternating radii keeps
// evenly-spaced nodes from forming one perfect, hard-to-read ring.
export function homePosition(index: number, total: number): Point {
  if (total <= 0) return { x: 50, y: 50 };
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  const radius = index % 2 === 0 ? 40 : 33;
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle) * 0.82,
  };
}

// How far (0-1) a neighbor should be pulled from its home position toward
// the anchor, given its similarity score (0-100). Curved (exponent > 1) so
// the difference between a 40 and a 70 reads clearly, never reaches 1 so a
// node never lands exactly on the anchor, and near-zero scores don't
// visibly drift at all.
export function pullFactor(score: number): number {
  if (score <= 5) return 0;
  return Math.min(0.86, Math.pow(score / 100, 1.15));
}

export function pulledPosition(home: Point, anchor: Point, score: number): Point {
  const t = pullFactor(score);
  return {
    x: home.x + (anchor.x - home.x) * t,
    y: home.y + (anchor.y - home.y) * t,
  };
}

export type SimilarityTier = 'near-duplicate' | 'strong' | 'related' | 'loose';

export function similarityTier(score: number): SimilarityTier {
  if (score >= 85) return 'near-duplicate';
  if (score >= 70) return 'strong';
  if (score >= 40) return 'related';
  return 'loose';
}

export const SIMILARITY_TIER_LABEL: Record<SimilarityTier, string> = {
  'near-duplicate': 'Near-duplicate',
  strong: 'Strong overlap',
  related: 'Related',
  loose: 'Loosely related',
};

export const SIMILARITY_TIER_COLOR: Record<SimilarityTier, { badge: string; dot: string; ring: string; text: string }> = {
  'near-duplicate': {
    badge: 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
    dot: 'bg-rose-500',
    ring: 'ring-rose-500/60',
    text: 'text-rose-600 dark:text-rose-400',
  },
  strong: {
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
    dot: 'bg-amber-500',
    ring: 'ring-amber-500/60',
    text: 'text-amber-600 dark:text-amber-400',
  },
  related: {
    badge: 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20',
    dot: 'bg-sky-500',
    ring: 'ring-sky-500/60',
    text: 'text-sky-600 dark:text-sky-400',
  },
  loose: {
    badge: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20',
    dot: 'bg-zinc-500',
    ring: 'ring-zinc-500/60',
    text: 'text-zinc-500 dark:text-zinc-400',
  },
};
