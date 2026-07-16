// Canonical Tailwind class strings for the provenance/epistemic/freshness
// badges shown across Badge.astro, TrustGlyph.astro, Wizard.tsx, and
// SkillExplorer.tsx. These used to be hand-copied in each file and had
// already drifted (official/partner provenance badges were dark:*-900/30 in
// some places and /40 in others) - this is the one place to change a color.
export interface Verdict {
  label: string;
  style: string;
  warn: boolean;
}

export const PROVENANCE_BADGE_CLASS: Record<string, string> = {
  official: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  partner: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  community: 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300',
};

export const EPISTEMIC_BADGE_CLASS = {
  reviewed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/30',
  unreviewed: 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-900/30',
};

export const FRESHNESS_BADGE_CLASS = {
  drifted: 'bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300 border border-red-200 dark:border-red-900/30',
  fresh: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-400 border border-zinc-200/50 dark:border-zinc-700/50',
};

export const LICENSE_BADGE_CLASS = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-400 border border-zinc-200/50 dark:border-zinc-700/50';

export function provenanceBadgeClass(provenance: string): string {
  return PROVENANCE_BADGE_CLASS[provenance] ?? PROVENANCE_BADGE_CLASS.community;
}

// "google" -> "Google", "anthropic" -> "Anthropic" - vendor strings in the
// data are already clean single words, so a plain capitalize covers every
// known and anticipated vendor without a per-vendor lookup table.
export function vendorLabel(vendor: string | null): string | null {
  if (!vendor) return null;
  return vendor.charAt(0).toUpperCase() + vendor.slice(1);
}

export function provenanceLabel(provenance: string, vendor: string | null): string {
  if (provenance === 'official') {
    const brand = vendorLabel(vendor) ?? 'Official';
    return `Official · ${brand}`;
  }
  return provenance.charAt(0).toUpperCase() + provenance.slice(1);
}

export function epistemicBadgeClass(reviewStatus: string): string {
  return reviewStatus === 'human_read' ? EPISTEMIC_BADGE_CLASS.reviewed : EPISTEMIC_BADGE_CLASS.unreviewed;
}

export function freshnessBadgeClass(freshness: string | null): string {
  return freshness === 'drifted' ? FRESHNESS_BADGE_CLASS.drifted : FRESHNESS_BADGE_CLASS.fresh;
}

export function formatBadgeDate(dateStr: string | null): string {
  if (!dateStr) return '';
  return dateStr.split('T')[0];
}

// The collapsed single-glyph verdict shown in place of four separate badges:
// reviewed + fresh is the only "trusted" state, everything else collapses to
// a lower-trust glyph with the full detail one click away.
export function trustVerdict(reviewStatus: string, freshness: string | null, provenance: string): Verdict {
  const isReviewed = reviewStatus === 'human_read';
  const isDrifted = freshness === 'drifted';
  const isOfficial = provenance === 'official' || provenance === 'partner';

  if (isDrifted) {
    return { label: 'Recheck pending', style: FRESHNESS_BADGE_CLASS.drifted, warn: true };
  }
  if (isReviewed) {
    return { label: "Editor's Choice", style: EPISTEMIC_BADGE_CLASS.reviewed, warn: false };
  }
  if (isOfficial) {
    return { label: 'Verified Publisher', style: PROVENANCE_BADGE_CLASS.official, warn: false };
  }
  return { label: 'Unverified', style: EPISTEMIC_BADGE_CLASS.unreviewed, warn: true };
}

