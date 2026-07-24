import { useState, useMemo, useRef, useEffect } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import { formatTokens } from '../utils/contextCost';
import { PHASE_COLORS, DEFAULT_PHASE_COLOR, type PhaseColor } from '../utils/phaseColors';
import { CAPABILITY_COLORS, DEFAULT_CAPABILITY_COLOR } from '../utils/capabilityColors';
import { provenanceBadgeClass, provenanceLabel, freshnessBadgeClass, vendorLabel as formatVendorLabel, formatBadgeDate } from '../utils/badgeStyles';
import type { Tool, Capability, KB, KBEntry, SkillRef } from '../types/kb';

// 'phase' groups the SDLC page by lifecycle_phase, keeping only skills that
// have one (the software-engineering-flavored subset). 'capability' groups
// everything else (lifecycle_phase === null) by its capability instead -
// the two modes partition the whole catalog with no overlap.
// 'publisher' groups everything by publisher/vendor.
type Mode = 'phase' | 'capability' | 'publisher';

interface Props {
  kb: KB;
  mode: Mode;
}

interface AxisGroup {
  id: string;
  label: string;
  order: number;
}

interface SkillItem {
  id: string;
  skill: SkillRef;
  // Undefined for a publisher-mode item whose skill was never assigned one
  // of the 8 curated capabilities (sourced from kb.all_skills, not
  // kb.entries) - there's no capability-level card to show for it.
  entry: KBEntry | undefined;
  capability: Capability | undefined;
  group: AxisGroup | undefined;
  isRecommended: boolean;
}

const PUBLISHERS: AxisGroup[] = [
  { id: 'google', label: 'Google', order: 1 },
  { id: 'anthropic', label: 'Anthropic', order: 2 },
  { id: 'vercel', label: 'Vercel', order: 3 },
  { id: 'nvidia', label: 'NVIDIA', order: 4 },
  { id: 'datadog', label: 'Datadog', order: 5 },
  { id: 'openai', label: 'OpenAI', order: 6 },
  { id: 'partner-other', label: 'Other Partners', order: 7 },
  { id: 'community', label: 'Community', order: 8 },
];

const PUBLISHER_COLORS: Record<string, PhaseColor> = {
  google: {
    accent: 'border-blue-500/20 hover:border-blue-500/85 dark:border-blue-500/10 dark:hover:border-blue-500/70',
    glow: 'rgba(59, 130, 246, 0.08)',
    badge: 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20',
    dot: 'bg-blue-500',
  },
  anthropic: {
    accent: 'border-amber-500/20 hover:border-amber-500/85 dark:border-amber-500/10 dark:hover:border-amber-500/70',
    glow: 'rgba(245, 158, 11, 0.08)',
    badge: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
    dot: 'bg-amber-500',
  },
  vercel: {
    accent: 'border-zinc-500/20 hover:border-zinc-500/85 dark:border-zinc-500/10 dark:hover:border-zinc-500/70',
    glow: 'rgba(113, 113, 122, 0.08)',
    badge: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20',
    dot: 'bg-zinc-500',
  },
  nvidia: {
    accent: 'border-emerald-500/20 hover:border-emerald-500/85 dark:border-emerald-500/10 dark:hover:border-emerald-500/70',
    glow: 'rgba(16, 185, 129, 0.08)',
    badge: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
    dot: 'bg-emerald-500',
  },
  datadog: {
    accent: 'border-purple-500/20 hover:border-purple-500/85 dark:border-purple-500/10 dark:hover:border-purple-500/70',
    glow: 'rgba(168, 85, 247, 0.08)',
    badge: 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/20',
    dot: 'bg-purple-500',
  },
  openai: {
    accent: 'border-teal-500/20 hover:border-teal-500/85 dark:border-teal-500/10 dark:hover:border-teal-500/70',
    glow: 'rgba(20, 184, 166, 0.08)',
    badge: 'bg-teal-500/10 text-teal-700 dark:text-teal-300 border-teal-500/20',
    dot: 'bg-teal-500',
  },
  'partner-other': {
    accent: 'border-indigo-500/20 hover:border-indigo-500/85 dark:border-indigo-500/10 dark:hover:border-indigo-500/70',
    glow: 'rgba(99, 102, 241, 0.08)',
    badge: 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/20',
    dot: 'bg-indigo-500',
  },
  community: {
    accent: 'border-orange-500/20 hover:border-orange-500/85 dark:border-orange-500/10 dark:hover:border-orange-500/70',
    glow: 'rgba(249, 115, 22, 0.08)',
    badge: 'bg-orange-500/10 text-orange-700 dark:text-orange-300 border-orange-500/20',
    dot: 'bg-orange-500',
  },
};

// Same prefix-stripping + Title Case + acronym rules the old static SDLC
// grid used, moved here since this island is now the only consumer.
const ACRONYMS = ['API', 'GKE', 'CLI', 'SDK', 'MCP', 'WAF', 'SQL', 'IAM', 'VM', 'HPC', 'DR', 'UI', 'XLSX', 'DOCX', 'PDF', 'PPTX'];
const VENDOR_PREFIXES: [string, number][] = [['google-', 7], ['anthropics-', 11], ['vercel-labs-', 12]];

function formatSkillName(name: string): string {
  let cleaned = name;
  for (const [prefix, len] of VENDOR_PREFIXES) {
    if (cleaned.startsWith(prefix)) {
      cleaned = cleaned.substring(len);
      break;
    }
  }
  return cleaned
    .split('-')
    .map(word => {
      const upper = word.toUpperCase();
      if (ACRONYMS.includes(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
}

function initials(name: string): string {
  const words = formatSkillName(name).split(' ').filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export default function SkillExplorer({ kb, mode }: Props) {
  const groupLabel = mode === 'phase' ? 'phase' : mode === 'capability' ? 'capability' : 'publisher';
  const colorMap = mode === 'phase' ? PHASE_COLORS : mode === 'capability' ? CAPABILITY_COLORS : PUBLISHER_COLORS;
  const defaultColor = mode === 'phase' ? DEFAULT_PHASE_COLOR : mode === 'capability' ? DEFAULT_CAPABILITY_COLOR : PUBLISHER_COLORS.community;

  const groups: AxisGroup[] = useMemo(
    () => [...(mode === 'publisher' ? PUBLISHERS : mode === 'phase' ? kb.lifecycle_phases : kb.capabilities)].sort((a, b) => a.order - b.order),
    [kb, mode]
  );
  const capabilityById = useMemo(() => {
    const map: Record<string, Capability> = {};
    for (const c of kb.capabilities) map[c.id] = c;
    return map;
  }, [kb]);
  const groupById = useMemo(() => {
    const map: Record<string, AxisGroup> = {};
    for (const g of groups) map[g.id] = g;
    return map;
  }, [groups]);
  const entryByCapabilityId = useMemo(() => {
    const map: Record<string, KBEntry> = {};
    for (const e of kb.entries) map[e.capability_id] = e;
    return map;
  }, [kb]);

  function publisherGroupId(skill: SkillRef): string {
    if (skill.vendor === 'google') return 'google';
    if (skill.vendor === 'anthropic') return 'anthropic';
    if (skill.vendor === 'vercel') return 'vercel';
    if (skill.vendor === 'nvidia') return 'nvidia';
    if (skill.vendor === 'datadog') return 'datadog';
    if (skill.vendor === 'openai') return 'openai';
    if (skill.provenance === 'official' || skill.provenance === 'partner') return 'partner-other';
    return 'community';
  }

  // Phase mode keeps only skills with a lifecycle_phase (the SDLC subset),
  // sourced from kb.entries (capability-assigned skills only) and grouped by
  // phase. Capability mode keeps the rest of kb.entries (no lifecycle_phase)
  // grouped by capability - the two modes never show the same skill.
  // Publisher mode sources from kb.all_skills instead: every active skill
  // regardless of capability assignment, grouped by vendor - a skill with no
  // capability still shows up here with `entry` left undefined.
  const items = useMemo(() => {
    const list: SkillItem[] = [];

    if (mode === 'publisher') {
      for (const [id, skill] of Object.entries(kb.all_skills)) {
        const capId = skill.capability_id;
        list.push({
          id,
          skill,
          entry: capId ? entryByCapabilityId[capId] : undefined,
          capability: capId ? capabilityById[capId] : undefined,
          group: groupById[publisherGroupId(skill)],
          isRecommended: capId ? entryByCapabilityId[capId]?.recommended.default === id : false,
        });
      }
    } else {
      for (const entry of kb.entries) {
        for (const [id, skill] of Object.entries(entry.skill_refs)) {
          if (mode === 'phase') {
            if (!skill.lifecycle_phase) continue;
          } else if (mode === 'capability') {
            if (skill.lifecycle_phase) continue;
          }

          const groupId = mode === 'phase' ? skill.lifecycle_phase! : entry.capability_id;

          list.push({
            id,
            skill,
            entry,
            capability: capabilityById[entry.capability_id],
            group: groupById[groupId],
            isRecommended: entry.recommended.default === id,
          });
        }
      }
    }

    return list.sort((a, b) => formatSkillName(a.skill.name).localeCompare(formatSkillName(b.skill.name)));
  }, [kb, mode, capabilityById, groupById, entryByCapabilityId]);

  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  // Sync publisher/group selection from URL parameter or hash fragment
  useEffect(() => {
    const handleURLChange = () => {
      const params = new URLSearchParams(window.location.search);
      const hash = window.location.hash.replace('#', '');
      const pubId = params.get('publisher') || params.get('group') || hash || null;
      if (pubId && groups.some(g => g.id === pubId)) {
        setSelectedGroup(pubId);
        // Scroll to explorer when a company is selected from the grid
        const explorerEl = document.getElementById('skill-explorer-main');
        if (explorerEl) {
          explorerEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    };
    
    handleURLChange();
    
    window.addEventListener('popstate', handleURLChange);
    window.addEventListener('hashchange', handleURLChange);
    return () => {
      window.removeEventListener('popstate', handleURLChange);
      window.removeEventListener('hashchange', handleURLChange);
    };
  }, [groups]);

  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [installTool, setInstallTool] = useState<string>(kb.tools[0]?.id ?? '');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredItems = useMemo(() => {
    return items.filter(item => {
      if (selectedGroup && item.group?.id !== selectedGroup) return false;
      if (!normalizedQuery) return true;
      const haystacks = [
        item.skill.name,
        formatSkillName(item.skill.name),
        item.entry?.card.title ?? '',
        item.entry?.card.what_it_does ?? item.skill.summary ?? '',
        item.capability?.label ?? '',
      ];
      return haystacks.some(h => h.toLowerCase().includes(normalizedQuery));
    });
  }, [items, selectedGroup, normalizedQuery]);

  const selected = useMemo(() => {
    if (selectedId) {
      const match = filteredItems.find(i => i.id === selectedId);
      if (match) return match;
    }
    return filteredItems[0] ?? null;
  }, [filteredItems, selectedId]);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  };

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    });
  };

  const groupCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of items) {
      if (!item.group) continue;
      counts[item.group.id] = (counts[item.group.id] || 0) + 1;
    }
    return counts;
  }, [items]);

  return (
    <div id="skill-explorer-main" className="space-y-6">
      {/* Filter bar: free-text search + group facets, mirroring a model
          browser's "search + left-nav category list" pattern in one row. */}
      <div className="bg-zinc-100/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 md:p-5 space-y-4">
        <div className="relative">
          <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
          </svg>
          <input
            type="text"
            value={query}
            onInput={(e) => setQuery(e.currentTarget.value)}
            placeholder={`Filter skills by name or ${groupLabel}...`}
            aria-label="Filter skills"
            className="w-full bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700 rounded pl-9 pr-9 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              aria-label="Clear filter"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedGroup(null)}
            className={`px-3 py-1.5 rounded-full text-xs font-mono font-medium border transition-colors ${
              selectedGroup === null
                ? 'bg-zinc-900 text-white border-zinc-900 dark:bg-white dark:text-zinc-900 dark:border-white'
                : 'bg-white dark:bg-zinc-950 text-zinc-600 dark:text-zinc-400 border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
            }`}
          >
            All {mode === 'phase' ? 'phases' : mode === 'capability' ? 'capabilities' : 'publishers'} &middot; {items.length}
          </button>
          {groups.map(group => {
            const colors = colorMap[group.id] || defaultColor;
            const active = selectedGroup === group.id;
            return (
              <button
                key={group.id}
                onClick={() => setSelectedGroup(active ? null : group.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono font-medium border transition-colors ${
                  active
                    ? `${colors.badge} border-current`
                    : 'bg-white dark:bg-zinc-950 text-zinc-600 dark:text-zinc-400 border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`}></span>
                {group.label} &middot; {groupCounts[group.id] || 0}
              </button>
            );
          })}
        </div>
      </div>

      {/* Master/detail: scrollable skill list on the left, full card detail
          panel on the right - one skill selected at a time, no page nav. */}
      <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6 items-start">
        {/* List pane */}
        <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-900 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 text-[11px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Showing {filteredItems.length} skill{filteredItems.length === 1 ? '' : 's'}
          </div>
          <div className="max-h-[32rem] lg:max-h-[70vh] overflow-y-auto divide-y divide-zinc-100 dark:divide-zinc-800/70">
            {filteredItems.length === 0 && (
              <p className="text-xs text-zinc-400 dark:text-zinc-600 italic text-center py-10 px-4">
                No skills match this filter.
              </p>
            )}
            {filteredItems.map(item => {
              const colors = item.group ? (colorMap[item.group.id] || defaultColor) : defaultColor;
              const isActive = selected?.id === item.id;
              const nutrition = item.skill.nutrition;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleSelect(item.id)}
                  aria-current={isActive}
                  className={`w-full text-left p-3.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset ${
                    isActive
                      ? 'bg-accent/5 dark:bg-accent/10 border-l-2 border-l-accent'
                      : 'border-l-2 border-l-transparent hover:bg-zinc-50 dark:hover:bg-zinc-800/40'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 leading-snug">
                      {formatSkillName(item.skill.name)}
                    </span>
                    {item.isRecommended && (
                      <span className="shrink-0 text-[9px] font-mono font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20">
                        Pick
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed mt-1 line-clamp-2">
                    {item.entry?.card.what_it_does ?? item.skill.summary ?? 'No description yet.'}
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    <span className={`inline-flex items-center gap-1 text-[9px] font-mono font-medium px-1.5 py-0.5 rounded border ${colors.badge}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`}></span>
                      {item.group?.label ?? 'Unclassified'}
                    </span>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border-zinc-200/50 dark:border-zinc-700/50 uppercase tracking-tight">
                      {item.skill.provenance}
                    </span>
                    {nutrition && nutrition.basis === 'body' && (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border bg-zinc-100 dark:bg-zinc-800/80 text-zinc-500 dark:text-zinc-400 border-zinc-200/50 dark:border-zinc-700/50">
                        &#9689; {formatTokens(nutrition.token_estimate)}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detail pane */}
        <div ref={detailRef} className="lg:sticky lg:top-24 scroll-mt-24">
          {selected ? (
            <SkillDetailPanel
              item={selected}
              mode={mode}
              colorMap={colorMap}
              defaultColor={defaultColor}
              tools={kb.tools}
              installTool={installTool}
              onInstallToolChange={setInstallTool}
              copiedKey={copiedKey}
              onCopy={handleCopy}
            />
          ) : (
            <div className="border border-dashed border-zinc-200 dark:border-zinc-800 rounded-xl p-12 text-center text-sm text-zinc-400 dark:text-zinc-600">
              Select a skill from the list to see its full detail card.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface ColorSet {
  accent: string;
  glow: string;
  badge: string;
  dot: string;
}

interface SkillDetailPanelProps {
  item: SkillItem;
  mode: Mode;
  colorMap: Record<string, ColorSet>;
  defaultColor: ColorSet;
  tools: Tool[];
  installTool: string;
  onInstallToolChange: (id: string) => void;
  copiedKey: string | null;
  onCopy: (text: string, key: string) => void;
}

function SkillDetailPanel({ item, mode, colorMap, defaultColor, tools, installTool, onInstallToolChange, copiedKey, onCopy }: SkillDetailPanelProps) {
  const { id, skill, entry, capability, group } = item;
  const colors = group ? (colorMap[group.id] || defaultColor) : defaultColor;
  const isReviewed = skill.review_status === 'human_read';
  const isDrifted = skill.freshness === 'drifted';
  const nutrition = skill.nutrition;
  const vendorLabel = formatVendorLabel(skill.vendor);
  const installCmd = skill.install[installTool];

  const isUnreviewedCommunity = skill.provenance === 'community' && skill.review_status !== 'human_read';
  const isVerifiedPublisher = (skill.provenance === 'official' || skill.provenance === 'partner') && skill.review_status !== 'human_read';
  const isEditorsChoice = skill.review_status === 'human_read';

  const cardBorderClass = isEditorsChoice
    ? 'border-emerald-300 dark:border-emerald-800 border-l-4 border-l-emerald-400 dark:border-l-emerald-500'
    : isVerifiedPublisher
    ? 'border-blue-300 dark:border-blue-800 border-l-4 border-l-blue-400 dark:border-l-blue-500'
    : 'border-amber-300 dark:border-amber-800 border-l-4 border-l-amber-400 dark:border-l-amber-500'; // Community unreviewed

  return (
    <div className={`border rounded-xl bg-white dark:bg-zinc-900 shadow-sm overflow-hidden ${cardBorderClass}`}>
      {isEditorsChoice && (
        <div className="px-6 py-2 bg-emerald-50 dark:bg-emerald-950/20 border-b border-emerald-200 dark:border-emerald-900/30 text-xs font-mono font-semibold text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
          <svg className="w-4.5 h-4.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          Editor's Choice — Manually reviewed and recommended by SkillDeck editors.
        </div>
      )}
      {isVerifiedPublisher && (
        <div className="px-6 py-2 bg-blue-50 dark:bg-blue-950/20 border-b border-blue-200 dark:border-blue-900/30 text-xs font-mono font-semibold text-blue-800 dark:text-blue-300 flex items-center gap-2">
          <svg className="w-4.5 h-4.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          Org Verified — Sourced directly from the official GitHub repository.
        </div>
      )}
      {isUnreviewedCommunity && (
        <div className="px-6 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-900/40 text-xs font-mono font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          Community Submission — Not yet human-reviewed. Verify contents before running.
        </div>
      )}
      {/* Header: avatar, name, verified/recommended badges, upstream link */}
      <div className="p-6 md:p-7 border-b border-zinc-200 dark:border-zinc-800 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3.5 min-w-0">
            <div
              className={`shrink-0 w-11 h-11 rounded-lg flex items-center justify-center text-sm font-bold font-mono ${colors.badge} border`}
            >
              {initials(skill.name)}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-xl md:text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
                  {formatSkillName(skill.name)}
                </h3>
                {isReviewed && (
                  <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-label="Human-reviewed">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              {vendorLabel && (
                <p className="text-xs font-mono text-zinc-400 dark:text-zinc-500 mt-0.5">{vendorLabel}</p>
              )}
            </div>
          </div>
          {item.isRecommended && (
            <span className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase tracking-wide bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-500/20">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 15.27L16.18 19l-1.64-7.03L20 7.24l-7.19-.61L10 0 7.19 6.63 0 7.24l5.46 4.73L3.82 19z" />
              </svg>
              Editor's Pick
            </span>
          )}
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs font-mono text-zinc-500 dark:text-zinc-400">
          <span className="inline-flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`}></span>
            {group?.label ?? 'Unclassified'}
          </span>
          {mode === 'phase' && capability && <span>{capability.label}</span>}
          <span>{skill.license}</span>
          {formatBadgeDate(skill.reviewed_at) && <span>Reviewed {formatBadgeDate(skill.reviewed_at)}</span>}
        </div>

        {/* Trust/provenance badges */}
        <div className="flex flex-wrap gap-2">
          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold font-mono uppercase tracking-wider ${provenanceBadgeClass(skill.provenance)}`}>
            {provenanceLabel(skill.provenance, skill.vendor)}
          </span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium font-mono ${
            isReviewed
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/30'
              : (skill.provenance === 'official' || skill.provenance === 'partner')
              ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 border border-blue-200 dark:border-blue-900/30'
              : 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-900/30'
          }`}>
            {isReviewed ? '✓ Editor Choice' : (skill.provenance === 'official' || skill.provenance === 'partner') ? '✓ Publisher Verified (No Review Needed)' : 'Auto-summarized — not yet reviewed'}
          </span>
          {isDrifted && (
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium font-mono ${freshnessBadgeClass(skill.freshness)}`}>
              Upstream changed — recheck pending
            </span>
          )}
        </div>
      </div>

      <div className="p-6 md:p-7 space-y-6">
        {/* Skill Information: key-value grid, LM-Studio "Model Information" style */}
        <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
          <div className="px-4 py-2 bg-zinc-50/70 dark:bg-zinc-800/40 border-b border-zinc-200 dark:border-zinc-800 text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Skill Information
          </div>
          <dl className="divide-y divide-zinc-100 dark:divide-zinc-800/70 text-sm">
            <InfoRow label="Skill ID">
              <div className="flex items-center gap-2 min-w-0">
                <code className="font-mono text-xs text-zinc-700 dark:text-zinc-300 truncate">{id}</code>
                <button
                  onClick={() => onCopy(id, `id-${id}`)}
                  aria-label="Copy skill ID"
                  className="shrink-0 text-zinc-400 hover:text-accent"
                >
                  {copiedKey === `id-${id}` ? (
                    <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                  )}
                </button>
              </div>
            </InfoRow>
            {mode === 'publisher' ? (
              <>
                <InfoRow label="Publisher">{group?.label ?? '—'}</InfoRow>
                <InfoRow label="Capability">{capability?.label ?? '—'}</InfoRow>
              </>
            ) : mode === 'phase' ? (
              <>
                <InfoRow label="Capability">{capability?.label ?? '—'}</InfoRow>
                <InfoRow label="Lifecycle phase">{group?.label ?? 'Unclassified'}</InfoRow>
              </>
            ) : (
              <InfoRow label="Capability">{group?.label ?? '—'}</InfoRow>
            )}
            <InfoRow label="License">{skill.license}</InfoRow>
            <InfoRow label="Context cost">
              {nutrition
                ? nutrition.basis === 'body'
                  ? formatTokens(nutrition.token_estimate)
                  : 'Size unknown — metadata only'
                : 'Not computed'}
            </InfoRow>
          </dl>
        </div>

        {/* What it does */}
        <div className="space-y-1">
          <span className="block text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            What it does
          </span>
          <p className="text-sm md:text-base text-zinc-600 dark:text-zinc-300 leading-relaxed">
            {entry?.card.what_it_does ?? skill.summary ?? 'No description yet — see the skill’s repository for details.'}
          </p>
          {nutrition?.trigger && (
            <p className="text-[11px] font-mono text-zinc-400 dark:text-zinc-500">
              Loads when: &ldquo;{nutrition.trigger}&rdquo;
            </p>
          )}
        </div>

        {/* Try saying - only available for skills with a capability-level
            Explainer Card; a skill outside the 8 capabilities has none. */}
        {entry && (
          <div className="space-y-2">
            <span className="block text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
              Try asking your assistant
            </span>
            <div className="relative group bg-accent/5 dark:bg-accent/10 border-2 border-accent/30 dark:border-accent/40 rounded p-4 flex items-center justify-between gap-4">
              <blockquote className="text-sm font-semibold italic text-zinc-800 dark:text-zinc-100">
                &ldquo;{entry.card.try_saying}&rdquo;
              </blockquote>
              <button
                onClick={() => onCopy(entry.card.try_saying, `prompt-${id}`)}
                className="px-3 py-1.5 rounded border border-accent bg-accent text-white hover:bg-accent-dark focus:outline-none focus:ring-2 focus:ring-accent flex items-center gap-1.5 text-xs font-mono font-semibold shrink-0"
                aria-label="Copy prompt example"
              >
                {copiedKey === `prompt-${id}` ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {/* Download Options, LM-Studio style: tool tabs + copyable install command */}
        <div className="space-y-2">
          <span className="block text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Install options
          </span>
          <div className="border border-zinc-200 dark:border-zinc-800 rounded overflow-hidden">
            <div className="flex border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 overflow-x-auto whitespace-nowrap">
              {tools.map(t => (
                <button
                  key={t.id}
                  onClick={() => onInstallToolChange(t.id)}
                  className={`px-3.5 py-2 text-xs font-mono border-b-2 -mb-[1px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset ${
                    installTool === t.id
                      ? 'border-accent text-accent font-semibold'
                      : 'border-transparent text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="bg-zinc-950 text-zinc-200 p-4 font-mono text-xs flex items-center justify-between gap-4 overflow-x-auto">
              {installCmd ? (
                <code className="whitespace-pre-wrap select-all leading-relaxed text-zinc-300">{installCmd}</code>
              ) : (
                <span className="text-zinc-500 italic">
                  See provider documentation: <a href={skill.repo_url} target="_blank" rel="noopener noreferrer" className="text-accent underline hover:text-accent-dark">GitHub Upstream</a>
                </span>
              )}
              {installCmd && (
                <button
                  onClick={() => onCopy(installCmd, `install-${id}`)}
                  className="p-1.5 rounded border border-zinc-800 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent shrink-0"
                  aria-label="Copy installation command"
                >
                  {copiedKey === `install-${id}` ? (
                    <svg className="w-4 h-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Footer: primary action out to the full SKILL.md documentation page */}
      <div className="px-6 md:px-7 py-4 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 flex flex-wrap items-center justify-between gap-3">
        <a
          href={skill.repo_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-mono text-zinc-400 hover:text-accent flex items-center gap-1"
        >
          View upstream source
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
        <a
          href={`/skill/${id}`}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded bg-accent text-white hover:bg-accent-dark text-xs font-mono font-semibold"
        >
          View full documentation
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </a>
      </div>
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: ComponentChildren }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 px-4 py-2.5 items-center">
      <dt className="text-xs font-mono text-zinc-400 dark:text-zinc-500">{label}</dt>
      <dd className="text-zinc-700 dark:text-zinc-300 min-w-0">{children}</dd>
    </div>
  );
}
