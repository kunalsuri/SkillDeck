// Tailwind class mappings and custom style helpers per SDLC phase.
export interface PhaseColor {
  accent: string;
  glow: string;
  badge: string;
  dot: string;
}

export const PHASE_COLORS: Record<string, PhaseColor> = {
  define: {
    accent: 'border-fuchsia-500/20 hover:border-fuchsia-500/85 dark:border-fuchsia-500/10 dark:hover:border-fuchsia-500/70',
    glow: 'rgba(217, 70, 239, 0.08)',
    badge: 'bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300 border-fuchsia-500/20',
    dot: 'bg-fuchsia-500',
  },
  plan: {
    accent: 'border-cyan-500/20 hover:border-cyan-500/85 dark:border-cyan-500/10 dark:hover:border-cyan-500/70',
    glow: 'rgba(6, 182, 212, 0.08)',
    badge: 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-500/20',
    dot: 'bg-cyan-500',
  },
  build: {
    accent: 'border-emerald-500/20 hover:border-emerald-500/85 dark:border-emerald-500/10 dark:hover:border-emerald-500/70',
    glow: 'rgba(16, 185, 129, 0.08)',
    badge: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  verify: {
    accent: 'border-amber-500/20 hover:border-amber-500/85 dark:border-amber-500/10 dark:hover:border-amber-500/70',
    glow: 'rgba(245, 158, 11, 0.08)',
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
    dot: 'bg-amber-500',
  },
  review: {
    accent: 'border-rose-500/20 hover:border-rose-500/85 dark:border-rose-500/10 dark:hover:border-rose-500/70',
    glow: 'rgba(244, 63, 94, 0.08)',
    badge: 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
    dot: 'bg-rose-500',
  },
  ship: {
    accent: 'border-indigo-500/20 hover:border-indigo-500/85 dark:border-indigo-500/10 dark:hover:border-indigo-500/70',
    glow: 'rgba(99, 102, 241, 0.08)',
    badge: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/20',
    dot: 'bg-indigo-500',
  },
};

export const DEFAULT_PHASE_COLOR: PhaseColor = {
  accent: 'border-zinc-500/20 hover:border-zinc-500/85 dark:border-zinc-500/10 dark:hover:border-zinc-500/70',
  glow: 'rgba(113, 113, 122, 0.08)',
  badge: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20',
  dot: 'bg-zinc-500',
};
