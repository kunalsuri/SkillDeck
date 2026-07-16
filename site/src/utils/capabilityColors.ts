// Tailwind class mappings and custom style helpers per capability, used by
// the General Skills explorer the same way phaseColors.ts drives the SDLC
// explorer. Kept in a separate palette so the two pages read as distinct
// "modes" of the same component rather than reusing one color per id.
import type { PhaseColor } from './phaseColors';

export const CAPABILITY_COLORS: Record<string, PhaseColor> = {
  documents: {
    accent: 'border-indigo-500/20 hover:border-indigo-500/85 dark:border-indigo-500/10 dark:hover:border-indigo-500/70',
    glow: 'rgba(99, 102, 241, 0.08)',
    badge: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/20',
    dot: 'bg-indigo-500',
  },
  'data-analysis': {
    accent: 'border-teal-500/20 hover:border-teal-500/85 dark:border-teal-500/10 dark:hover:border-teal-500/70',
    glow: 'rgba(20, 184, 166, 0.08)',
    badge: 'bg-teal-500/10 text-teal-700 dark:text-teal-300 border-teal-500/20',
    dot: 'bg-teal-500',
  },
  frontend: {
    accent: 'border-emerald-500/20 hover:border-emerald-500/85 dark:border-emerald-500/10 dark:hover:border-emerald-500/70',
    glow: 'rgba(16, 185, 129, 0.08)',
    badge: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  'cloud-ops': {
    accent: 'border-sky-500/20 hover:border-sky-500/85 dark:border-sky-500/10 dark:hover:border-sky-500/70',
    glow: 'rgba(14, 165, 233, 0.08)',
    badge: 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20',
    dot: 'bg-sky-500',
  },
  testing: {
    accent: 'border-amber-500/20 hover:border-amber-500/85 dark:border-amber-500/10 dark:hover:border-amber-500/70',
    glow: 'rgba(245, 158, 11, 0.08)',
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
    dot: 'bg-amber-500',
  },
  planning: {
    accent: 'border-violet-500/20 hover:border-violet-500/85 dark:border-violet-500/10 dark:hover:border-violet-500/70',
    glow: 'rgba(139, 92, 246, 0.08)',
    badge: 'bg-violet-500/10 text-violet-700 dark:text-violet-300 border-violet-500/20',
    dot: 'bg-violet-500',
  },
  'agent-building': {
    accent: 'border-fuchsia-500/20 hover:border-fuchsia-500/85 dark:border-fuchsia-500/10 dark:hover:border-fuchsia-500/70',
    glow: 'rgba(217, 70, 239, 0.08)',
    badge: 'bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-500/20',
    dot: 'bg-fuchsia-500',
  },
  design: {
    accent: 'border-rose-500/20 hover:border-rose-500/85 dark:border-rose-500/10 dark:hover:border-rose-500/70',
    glow: 'rgba(244, 63, 94, 0.08)',
    badge: 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
    dot: 'bg-rose-500',
  },
};

export const DEFAULT_CAPABILITY_COLOR: PhaseColor = {
  accent: 'border-zinc-500/20 hover:border-zinc-500/85 dark:border-zinc-500/10 dark:hover:border-zinc-500/70',
  glow: 'rgba(113, 113, 122, 0.08)',
  badge: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20',
  dot: 'bg-zinc-500',
};
