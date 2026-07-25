import { useState, useMemo, useRef, useEffect } from 'preact/hooks';
import type { KB, RelatedSkill } from '../types/kb';
import {
  homePosition, pulledPosition, similarityTier,
  SIMILARITY_TIER_LABEL, SIMILARITY_TIER_COLOR, type Point,
} from '../utils/similarityLayout';

interface Props {
  kb: KB;
}

const NAME_PREFIXES = [
  'google-', 'anthropics-', 'vercel-labs-', 'openai-', 'nvidia-',
  'datadog-labs-', 'block-', 'addyosmani-', 'kunalsuri-', 'github-',
];

function formatName(name: string): string {
  let cleaned = name;
  for (const prefix of NAME_PREFIXES) {
    if (cleaned.startsWith(prefix)) {
      cleaned = cleaned.slice(prefix.length);
      break;
    }
  }
  return cleaned
    .split(/[-_]/)
    .filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function clientToPercent(clientX: number, clientY: number, el: HTMLDivElement): Point {
  const rect = el.getBoundingClientRect();
  return {
    x: Math.min(96, Math.max(4, ((clientX - rect.left) / rect.width) * 100)),
    y: Math.min(96, Math.max(4, ((clientY - rect.top) / rect.height) * 100)),
  };
}

export default function SimilarityGalaxy({ kb }: Props) {
  // Scope: only skills the kitchen's similarity stage actually scored -
  // active skills with a real Skill Summary and one of the 8 curated
  // capabilities (kitchen/simmatrix.py: _eligible_skills). Everything else
  // has an empty `related` list rather than a fabricated one.
  const eligible = useMemo(
    () => Object.entries(kb.all_skills)
      .filter(([, s]) => (s.related?.length ?? 0) > 0)
      .sort((a, b) => formatName(a[1].name).localeCompare(formatName(b[1].name))),
    [kb]
  );

  const defaultAnchorId = useMemo(() => {
    if (eligible.length === 0) return null;
    return eligible.reduce((best, [id, s]) =>
      (s.related?.length ?? 0) > (kb.all_skills[best]?.related?.length ?? 0) ? id : best,
      eligible[0][0]
    );
  }, [eligible, kb]);

  const [anchorId, setAnchorId] = useState<string | null>(defaultAnchorId);
  const [threshold, setThreshold] = useState(40);
  const [selectedNeighborId, setSelectedNeighborId] = useState<string | null>(null);
  const [dragPos, setDragPos] = useState<Point | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (e: PointerEvent) => {
      if (containerRef.current) setDragPos(clientToPercent(e.clientX, e.clientY, containerRef.current));
    };
    const handleUp = () => setIsDragging(false);
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [isDragging]);

  const anchor = anchorId ? kb.all_skills[anchorId] : null;
  const allNeighbors: RelatedSkill[] = anchor?.related ?? [];
  const visibleNeighbors = useMemo(
    () => allNeighbors.filter(n => n.score >= threshold),
    [allNeighbors, threshold]
  );

  const selected = useMemo(() => {
    if (selectedNeighborId) {
      const match = visibleNeighbors.find(n => n.id === selectedNeighborId);
      if (match) return match;
    }
    return visibleNeighbors[0] ?? null;
  }, [visibleNeighbors, selectedNeighborId]);

  const anchorPos = dragPos ?? { x: 50, y: 50 };

  function goToAnchor(id: string) {
    setAnchorId(id);
    setDragPos(null);
    setSelectedNeighborId(null);
  }

  if (eligible.length === 0 || !anchor) {
    return (
      <div className="border border-dashed border-zinc-200 dark:border-zinc-800 rounded-xl p-12 text-center text-sm text-zinc-400 dark:text-zinc-600">
        No similarity data yet — run <code className="font-mono">python -m kitchen simmatrix-prepare</code> /
        <code className="font-mono"> simmatrix-apply</code> / <code className="font-mono">emit</code>.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Controls: anchor picker + threshold slider */}
      <div className="bg-zinc-100/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 md:p-5 flex flex-col md:flex-row gap-4 md:items-center md:justify-between">
        <div className="flex-1 min-w-0 space-y-1.5">
          <label htmlFor="anchor-select" className="block text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Skill to explore
          </label>
          <select
            id="anchor-select"
            value={anchorId ?? ''}
            onChange={(e) => goToAnchor(e.currentTarget.value)}
            className="w-full bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {eligible.map(([id, s]) => (
              <option key={id} value={id}>{formatName(s.name)}</option>
            ))}
          </select>
        </div>
        <div className="md:w-72 space-y-1.5">
          <label htmlFor="threshold-range" className="flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            <span>Minimum similarity</span>
            <span className="text-zinc-600 dark:text-zinc-300 font-semibold">{threshold}%</span>
          </label>
          <input
            id="threshold-range"
            type="range"
            min={0}
            max={95}
            step={5}
            value={threshold}
            onInput={(e) => setThreshold(Number(e.currentTarget.value))}
            className="w-full accent-accent"
          />
        </div>
      </div>

      {/* Galaxy canvas */}
      <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-900 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50 flex items-center justify-between gap-3">
          <span className="text-[11px] font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Drag the center skill — closer neighbors pull in harder
          </span>
          <button
            type="button"
            onClick={() => setDragPos(null)}
            className="text-[11px] font-mono text-zinc-400 hover:text-accent shrink-0"
          >
            Reset position
          </button>
        </div>

        <div
          ref={containerRef}
          className="relative w-full aspect-[16/10] select-none touch-none bg-[radial-gradient(circle_at_50%_50%,rgba(37,99,235,0.05),transparent_65%)]"
        >
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none">
            {visibleNeighbors.map(n => {
              const pos = pulledPosition(homePosition(allNeighbors.indexOf(n), allNeighbors.length), anchorPos, n.score);
              const tier = similarityTier(n.score);
              return (
                <line
                  key={n.id}
                  x1={anchorPos.x} y1={anchorPos.y}
                  x2={pos.x} y2={pos.y}
                  stroke="currentColor"
                  strokeWidth={0.15 + (n.score / 100) * 0.55}
                  className={SIMILARITY_TIER_COLOR[tier].text}
                  opacity={0.35 + (n.score / 100) * 0.4}
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
          </svg>

          {visibleNeighbors.length === 0 && (
            <p className="absolute inset-0 flex items-center justify-center text-xs text-zinc-400 dark:text-zinc-600 italic px-8 text-center">
              No neighbors at or above {threshold}% for this skill — lower the threshold.
            </p>
          )}

          {visibleNeighbors.map(n => {
            const home = homePosition(allNeighbors.indexOf(n), allNeighbors.length);
            const pos = pulledPosition(home, anchorPos, n.score);
            const tier = similarityTier(n.score);
            const colors = SIMILARITY_TIER_COLOR[tier];
            const isSelected = selected?.id === n.id;
            return (
              <button
                key={n.id}
                type="button"
                title={`${formatName(n.name)} — ${n.score}% similar`}
                onClick={() => setSelectedNeighborId(n.id)}
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                className={`absolute -translate-x-1/2 -translate-y-1/2 transition-[left,top] duration-200 ease-out flex flex-col items-center gap-1 focus:outline-none group`}
              >
                <span
                  className={`block rounded-full border-2 ${colors.dot} ${isSelected ? `ring-2 ${colors.ring} ring-offset-2 ring-offset-white dark:ring-offset-zinc-900` : ''} group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-white dark:group-focus-visible:ring-offset-zinc-900`}
                  style={{
                    width: `${14 + (n.score / 100) * 16}px`,
                    height: `${14 + (n.score / 100) * 16}px`,
                    borderColor: 'white',
                  }}
                />
                <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-white/90 dark:bg-zinc-900/90 text-zinc-600 dark:text-zinc-300 whitespace-nowrap shadow-sm border border-zinc-200/60 dark:border-zinc-700/60 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity">
                  {formatName(n.name)} · {n.score}%
                </span>
              </button>
            );
          })}

          {/* Anchor node: the one thing the user drags */}
          <div
            onPointerDown={(e) => {
              e.preventDefault();
              setIsDragging(true);
              if (containerRef.current) setDragPos(clientToPercent(e.clientX, e.clientY, containerRef.current));
            }}
            style={{ left: `${anchorPos.x}%`, top: `${anchorPos.y}%` }}
            className={`absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1 cursor-grab active:cursor-grabbing z-10 ${isDragging ? '' : 'transition-[left,top] duration-300 ease-out'}`}
          >
            <span className="block w-9 h-9 rounded-full bg-accent border-4 border-white dark:border-zinc-900 shadow-lg" />
            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-accent text-white whitespace-nowrap shadow-sm">
              {formatName(anchor.name)}
            </span>
          </div>
        </div>
      </div>

      {/* Explanation panel: what's shared, what differs, what drove the score */}
      {selected ? (
        <SimilarityDetail anchorName={formatName(anchor.name)} neighbor={selected} onExplore={() => goToAnchor(selected.id)} />
      ) : null}

      <p className="text-[11px] font-mono text-zinc-400 dark:text-zinc-600 text-center">
        Comparing {eligible.length} of {Object.keys(kb.all_skills).length} catalog skills — those with a written Skill
        Summary and a curated capability. Scores come from an agent reading each pair's summary, shortlisted by a
        deterministic keyword-overlap prefilter; they are judgments, not a calibrated probability.
      </p>
    </div>
  );
}

function SimilarityDetail({ anchorName, neighbor, onExplore }: { anchorName: string; neighbor: RelatedSkill; onExplore: () => void }) {
  const tier = similarityTier(neighbor.score);
  const colors = SIMILARITY_TIER_COLOR[tier];
  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-xl bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <h3 className="text-base md:text-lg font-bold text-zinc-900 dark:text-white truncate">
            {anchorName} <span className="text-zinc-400 dark:text-zinc-600 font-normal">vs</span> {formatName(neighbor.name)}
          </h3>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`px-2.5 py-1 rounded-full text-xs font-mono font-bold border ${colors.badge}`}>
            {neighbor.score}% · {SIMILARITY_TIER_LABEL[tier]}
          </span>
        </div>
      </div>

      <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <span className="block text-[10px] font-mono uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            What they share
          </span>
          <ul className="space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300 list-disc list-inside">
            {neighbor.shared_elements.map((el, i) => <li key={i}>{el}</li>)}
          </ul>
          {neighbor.shared_keywords.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {neighbor.shared_keywords.map(kw => (
                <code key={kw} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20">
                  {kw}
                </code>
              ))}
            </div>
          )}
        </div>
        <div className="space-y-2">
          <span className="block text-[10px] font-mono uppercase tracking-widest text-amber-600 dark:text-amber-400">
            How they differ
          </span>
          <ul className="space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300 list-disc list-inside">
            {neighbor.key_differences.map((el, i) => <li key={i}>{el}</li>)}
          </ul>
        </div>
      </div>

      <div className="px-6 pb-5 space-y-4">
        <p className="text-sm italic text-zinc-500 dark:text-zinc-400 border-l-2 border-zinc-200 dark:border-zinc-700 pl-3">
          {neighbor.reason}
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onExplore}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded border border-accent text-accent hover:bg-accent hover:text-white text-xs font-mono font-semibold transition-colors"
          >
            Explore from {formatName(neighbor.name)} →
          </button>
          <a
            href={`/skill/${neighbor.id}`}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-accent text-white hover:bg-accent-dark text-xs font-mono font-semibold"
          >
            Open full skill page ↗
          </a>
        </div>
      </div>
    </div>
  );
}
