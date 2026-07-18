import { useMemo, useState } from 'preact/hooks';
import type { JSX } from 'preact';
import { parseSkillMd, estimateTokens, diagnose, verdict, extractTrigger, type Finding } from '../utils/skillDoctor';
import { formatTokens } from '../utils/contextCost';

const SEVERITY_ORDER: Finding['severity'][] = ['error', 'warn', 'info'];

const VERDICT_STYLE: Record<ReturnType<typeof verdict>, string> = {
  ready: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300 border-emerald-200/50 dark:border-emerald-900/20',
  'needs-work': 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-900/30',
  blocked: 'bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-900/30',
};

const VERDICT_LABEL: Record<ReturnType<typeof verdict>, string> = {
  ready: 'Ready',
  'needs-work': 'Needs work',
  blocked: 'Blocked',
};

const SEVERITY_CARD_STYLE: Record<Finding['severity'], string> = {
  error: 'border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/20',
  warn: 'border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20',
  info: 'border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/40',
};

export default function Doctor() {
  const [text, setText] = useState('');
  const [textToDiagnose, setTextToDiagnose] = useState('');
  const [hasDiagnosed, setHasDiagnosed] = useState(false);
  const [activeTab, setActiveTab] = useState<'analysis' | 'guide' | 'rules'>('analysis');

  const handleInput = (e: JSX.TargetedEvent<HTMLTextAreaElement>) => {
    const val = e.currentTarget.value;
    setText(val);
    if (val.trim().length === 0) {
      setTextToDiagnose('');
      setHasDiagnosed(false);
    }
  };

  const handleCheck = () => {
    setTextToDiagnose(text);
    setHasDiagnosed(true);
    setActiveTab('analysis');
  };

  const isInputEmpty = text.trim().length === 0;

  const parsed = useMemo(() => parseSkillMd(textToDiagnose), [textToDiagnose]);
  const findings = useMemo(() => (hasDiagnosed && textToDiagnose.trim().length > 0 ? diagnose(textToDiagnose) : []), [textToDiagnose, hasDiagnosed]);
  const overallVerdict = useMemo(() => verdict(findings), [findings]);

  const bodyTokens = estimateTokens(parsed.body);
  const bodyWords = parsed.body.trim() ? parsed.body.trim().split(/\s+/).length : 0;
  const trigger = parsed.frontmatter.description ? extractTrigger(parsed.frontmatter.description) : '';

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: findings.filter((f) => f.severity === severity),
  })).filter((g) => g.items.length > 0);

  const errorCount = findings.filter((f) => f.severity === 'error').length;
  const warnCount = findings.filter((f) => f.severity === 'warn').length;

  const renderAnalysis = () => {
    if (!hasDiagnosed) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-center py-12 space-y-4">
          <div className="w-12 h-12 rounded-full bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center text-blue-600 dark:text-blue-400">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" className="w-6 h-6">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 18a3.75 3.75 0 00.495-7.467 5.99 5.99 0 00-1.925 3.546 5.974 5.974 0 01-2.133-1A3.75 3.75 0 0012 18z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75zm-.375 0h.008v.015h-.008V9.75zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75zm-.375 0h.008v.015h-.008V9.75z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-.778.099-1.533.284-2.253" />
            </svg>
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-150">Ready to Analyze</h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-[280px]">
              Paste your <code>SKILL.md</code> code on the left and click &ldquo;Check Skill&rdquo; to execute structural linting.
            </p>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-6 animate-fadeIn">
        {/* Verdict Banner */}
        <div className={`p-4 rounded-xl border flex gap-3 ${VERDICT_STYLE[overallVerdict]}`}>
          {overallVerdict === 'ready' && (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0 text-emerald-600 dark:text-emerald-400">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd" />
            </svg>
          )}
          {overallVerdict === 'needs-work' && (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0 text-amber-600 dark:text-amber-400">
              <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a.75.75 0 100-1.5.75.75 0 000 1.5z" clip-rule="evenodd" />
            </svg>
          )}
          {overallVerdict === 'blocked' && (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 flex-shrink-0 text-red-600 dark:text-red-400">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
            </svg>
          )}
          <div className="space-y-1">
            <div className="text-sm font-bold">{VERDICT_LABEL[overallVerdict]}</div>
            <div className="text-xs opacity-90 leading-normal">
              {overallVerdict === 'ready' && 'Ready to index! Your skill conforms to all structural formatting rules.'}
              {overallVerdict === 'needs-work' && 'Your skill has warnings that might cause issues with trigger matching. Refinement is recommended.'}
              {overallVerdict === 'blocked' && 'Errors must be resolved before this skill can be loaded.'}
            </div>
            <div className="text-[10px] font-mono opacity-70">
              {errorCount} error{errorCount === 1 ? '' : 's'}, {warnCount} warning{warnCount === 1 ? '' : 's'}
            </div>
          </div>
        </div>

        {/* Metrics Box */}
        <div className="bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-850 rounded-xl p-4 flex flex-wrap gap-x-6 gap-y-2 text-[11px] font-mono text-zinc-550 dark:text-zinc-400">
          <div>
            <span className="text-zinc-400 dark:text-zinc-600">Tokens:</span>{' '}
            <strong className="text-zinc-700 dark:text-zinc-300">{formatTokens(bodyTokens)}</strong>
          </div>
          <div>
            <span className="text-zinc-400 dark:text-zinc-600">Words:</span>{' '}
            <strong className="text-zinc-700 dark:text-zinc-300">{bodyWords}</strong>
          </div>
          {trigger && (
            <div className="w-full mt-1 pt-1.5 border-t border-zinc-200/60 dark:border-zinc-800/60 truncate">
              <span className="text-zinc-400 dark:text-zinc-600">Trigger:</span>{' '}
              <span className="text-zinc-700 dark:text-zinc-300 italic font-sans">&ldquo;{trigger}&rdquo;</span>
            </div>
          )}
        </div>

        {/* Findings List */}
        {findings.length === 0 ? (
          <div className="text-center py-8 text-zinc-400 dark:text-zinc-600 text-xs">
            ✨ No warnings or errors found. Excellent work!
          </div>
        ) : (
          <div className="space-y-3">
            <h4 className="text-xs font-bold font-mono uppercase tracking-widest text-zinc-400 dark:text-zinc-500">Lint Findings</h4>
            <div className="space-y-3">
              {groups.map((group) => (
                <div key={group.severity} className="space-y-3">
                  {group.items.map((f) => (
                    <div key={f.id} className={`border rounded-xl p-4 shadow-sm leading-relaxed ${SEVERITY_CARD_STYLE[f.severity]}`}>
                      <div className="flex justify-between items-center gap-2">
                        <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                          {f.id}
                        </span>
                        <span className={`text-[9px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                          f.severity === 'error' ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400' :
                          f.severity === 'warn' ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400' :
                          'bg-zinc-150 text-zinc-750 dark:bg-zinc-800 dark:text-zinc-400'
                        }`}>
                          {f.severity}
                        </span>
                      </div>
                      <div className="mt-2 text-xs font-bold text-zinc-900 dark:text-zinc-150">{f.title}</div>
                      <div className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-455 leading-normal">{f.detail}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderGuide = () => {
    return (
      <div className="space-y-6 text-xs leading-relaxed text-zinc-650 dark:text-zinc-350 animate-fadeIn">
        <div className="space-y-2">
          <h4 className="text-sm font-bold text-zinc-900 dark:text-white flex items-center gap-1.5">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-blue-500">
              <path fill-rule="evenodd" d="M10 2a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 2zm0 13a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 15zm0-6.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" clip-rule="evenodd" />
              <path fill-rule="evenodd" d="M12.728 3.772a.75.75 0 010 1.06l-1.061 1.06a.75.75 0 11-1.06-1.06l1.06-1.06a.75.75 0 011.061 0zm-5.456 5.456a.75.75 0 010 1.06l-1.06 1.06a.75.75 0 11-1.06-1.06l1.06-1.06a.75.75 0 011.06 0zM18 10a.75.75 0 01.75-.75h1.5a.75.75 0 010 1.5h-1.5A.75.75 0 0118 10zM1.25 10a.75.75 0 01.75-.75h1.5a.75.75 0 010 1.5H2a.75.75 0 01-.75-.75zm11.478 2.728a.75.75 0 010 1.06l-1.06 1.06a.75.75 0 11-1.061-1.06l1.06-1.06a.75.75 0 011.06 0zm-5.456 5.456a.75.75 0 010 1.06l-1.061 1.06a.75.75 0 11-1.06-1.06l1.06-1.061a.75.75 0 011.06 0zM10 8.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3z" clip-rule="evenodd" />
            </svg>
            Progressive Disclosure
          </h4>
          <p>
            Agent Skills load sequentially to minimize token footprints:
          </p>
          <ul className="list-disc pl-4 space-y-1 bg-zinc-50 dark:bg-zinc-950 p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 font-mono text-[10px] text-zinc-500 dark:text-zinc-450">
            <li><strong className="text-zinc-800 dark:text-zinc-250">Discovery</strong>: Startup loads only the name and description.</li>
            <li><strong className="text-zinc-800 dark:text-zinc-250">Activation</strong>: Full instructions load only when a task matches.</li>
            <li><strong className="text-zinc-800 dark:text-zinc-250">Execution</strong>: Follows instructions, executing scripts or referencing files.</li>
          </ul>
        </div>

        <div className="space-y-2">
          <h4 className="text-sm font-bold text-zinc-900 dark:text-white flex items-center gap-1.5">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-indigo-500">
              <path fill-rule="evenodd" d="M12.577 4.878a.75.75 0 01.919-.53l4.78 1.281a.75.75 0 01.53.919l-1.281 4.78a.75.75 0 01-1.449-.387l.81-3.022-11.232 11.232a.75.75 0 01-1.06-1.06L15.92 7.02l-3.022.81a.75.75 0 01-.321-1.449l4.78-1.281a.75.75 0 00.919-.53z" clip-rule="evenodd" />
            </svg>
            Best Practices for Creators
          </h4>
          <ul className="list-disc pl-4 space-y-2">
            <li>
              <strong>Spend context wisely</strong>: Omit general topics the agent knows. Keep descriptions thin and files under 500 lines or 5,000 tokens. Move extensive documentation to references.
            </li>
            <li>
              <strong>Favor procedures over declarations</strong>: Instruct the agent <em>how to approach</em> a class of problems (logical steps) instead of providing a hardcoded answer for a single task.
            </li>
            <li>
              <strong>Match specificity to fragility</strong>: Allow freedom in flexible pathways but be highly prescriptive with checklists or rigid commands for database migrations or destructive processes.
            </li>
            <li>
              <strong>Incorporate Gotchas sections</strong>: Place quirks, soft-delete record constraints, and multi-service ID conversions inside a Gotchas section to prevent logical failures.
            </li>
          </ul>
        </div>

        <div className="pt-4 border-t border-zinc-200 dark:border-zinc-800 space-y-2">
          <p className="text-[11px] text-zinc-500">
            For complete technical guidelines, templates, and reference materials, consult the official documentation:
          </p>
          <div className="flex flex-col gap-2 pt-1 font-mono text-[10px]">
            <a
              href="https://agentskills.io/home"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline font-semibold"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                <path fill-rule="evenodd" d="M12.24 10.285V11.5h.76c.465 0 .84.375.84.84v2.82a.84.84 0 01-.84.84H6.326a.84.84 0 01-.84-.84v-2.82c0-.465.375-.84.84-.84h.76v-1.215a4.24 4.24 0 018.48 0zM10.74 10.285a2.74 2.74 0 00-5.48 0V11.5h5.48v-1.215z" clip-rule="evenodd" />
              </svg>
              Agent Skills Specification (agentskills.io) &rarr;
            </a>
            <a
              href="https://agentskills.io/skill-creation/best-practices"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline font-semibold"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd" />
              </svg>
              Skill Creation Best Practices Guide &rarr;
            </a>
          </div>
        </div>
      </div>
    );
  };

  const renderRules = () => {
    const rulesList = [
      { id: 'SD01', severity: 'error', name: 'Missing Frontmatter Block', desc: 'SKILL.md must start and close with a "---" fence to isolate YAML properties.' },
      { id: 'SD02', severity: 'error', name: 'Missing Name Field', desc: 'Add a name: field to the frontmatter properties. This serves as a unique skill ID.' },
      { id: 'SD03', severity: 'warn', name: 'Invalid Name Formatting', desc: 'Skill IDs must be kebab-case (lowercase, digits, single hyphens) and under 64 characters.' },
      { id: 'SD04', severity: 'error', name: 'Missing Description Field', desc: 'Add a description: field to guide the harness during progressive activation matching.' },
      { id: 'SD05', severity: 'warn', name: 'Description Too Short', desc: 'Ensure descriptions are at least 80 characters long so the harness has enough context.' },
      { id: 'SD06', severity: 'warn', name: 'Description Too Long', desc: 'Trim description text under 1024 characters to prevent crowding the context window.' },
      { id: 'SD07', severity: 'warn', name: 'Missing Trigger Phrasing', desc: 'Descriptions must contain trigger prefixes like "Use this when..." or "Use for..." so activation logic works.' },
      { id: 'SD08', severity: 'warn', name: 'First Person Voice', desc: 'Descriptions should be authored in third person ("Performs code search...") rather than first person ("I do code search...").' },
      { id: 'SD09', severity: 'info', name: 'Body Size limit', desc: 'Warns if instructions exceed ~5,000 tokens. Move detailed guides to reference files.' },
      { id: 'SD10', severity: 'warn', name: 'Override Phrasing', desc: 'Flags words like "ignore previous instructions" which present prompt-injection risks.' },
      { id: 'SD11', severity: 'info', name: 'Empty Instructions Body', desc: 'Triggers when no instructions are provided in the body below the frontmatter.' },
    ];

    return (
      <div className="space-y-4 animate-fadeIn">
        <p className="text-[11px] text-zinc-500 leading-normal">
          The structural validation linter enforces 11 rules to verify indexing compatibility:
        </p>
        <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
          {rulesList.map((rule) => (
            <div key={rule.id} className="p-3 border border-zinc-200 dark:border-zinc-800 rounded-lg space-y-1 bg-zinc-50/50 dark:bg-zinc-950/20 text-xs">
              <div className="flex justify-between items-baseline flex-wrap gap-1">
                <span className="font-mono font-bold text-zinc-800 dark:text-zinc-250 flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    rule.severity === 'error' ? 'bg-red-500' :
                    rule.severity === 'warn' ? 'bg-amber-500' : 'bg-blue-500'
                  }`} />
                  {rule.id}: {rule.name}
                </span>
                <span className={`text-[8px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                  rule.severity === 'error' ? 'bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400' :
                  rule.severity === 'warn' ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400' :
                  'bg-blue-100 text-blue-700 dark:bg-blue-950/30 dark:text-blue-400'
                }`}>
                  {rule.severity}
                </span>
              </div>
              <p className="text-[11px] text-zinc-550 dark:text-zinc-400 leading-normal">{rule.desc}</p>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
      {/* Left Column: Editor-like Textarea Card */}
      <div className="lg:col-span-7 space-y-4">
        <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden shadow-sm focus-within:shadow-md transition-shadow duration-200">
          {/* Header Bar */}
          <div className="bg-zinc-50 dark:bg-zinc-950 border-b border-zinc-200 dark:border-zinc-800 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-red-400"></span>
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-400"></span>
              <span className="w-2.5 h-2.5 rounded-full bg-green-400"></span>
              <span className="ml-2 text-xs font-mono font-semibold text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5 bg-zinc-150/60 dark:bg-zinc-800 px-2.5 py-0.5 rounded border border-zinc-250 dark:border-zinc-750">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                  <path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clip-rule="evenodd" />
                </svg>
                SKILL.md
              </span>
            </div>
            {/* Counts */}
            <div className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 flex gap-3">
              <span>{text.length} chars</span>
              <span>{text.trim() ? text.trim().split(/\s+/).length : 0} words</span>
            </div>
          </div>

          {/* Textarea */}
          <textarea
            id="skill-doctor-input"
            value={text}
            onInput={handleInput}
            rows={18}
            spellcheck={false}
            placeholder={'---\nname: my-skill\ndescription: Use this when...\n---\n\nInstructions go here.'}
            className="w-full bg-transparent border-0 rounded-none p-5 text-sm font-mono leading-relaxed focus:outline-none focus:ring-0 dark:text-zinc-200 placeholder-zinc-350 dark:placeholder-zinc-650 resize-y"
          />
        </div>

        {/* Action bar below textarea card */}
        <div className="flex items-center gap-4 flex-wrap justify-between">
          <button
            onClick={handleCheck}
            disabled={isInputEmpty}
            className={`px-6 py-3 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center gap-2 ${
              isInputEmpty
                ? 'bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-600 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white shadow-sm hover:shadow-md hover:-translate-y-0.5'
            }`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.25a.75.75 0 00-1.5 0v2.5h-2.5a.75.75 0 000 1.5h2.5v2.5a.75.75 0 001.5 0v-2.5h2.5a.75.75 0 000-1.5h-2.5v-2.5z" clip-rule="evenodd" />
            </svg>
            Check Skill
          </button>

          {hasDiagnosed && text !== textToDiagnose && (
            <span className="text-xs font-mono text-amber-600 dark:text-amber-400 flex items-center gap-1.5 animate-pulse bg-amber-50 dark:bg-amber-950/20 border border-amber-200/50 dark:border-amber-900/30 px-3 py-2 rounded-lg">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 flex-shrink-0">
                <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a.75.75 0 100-1.5.75.75 0 000 1.5z" clip-rule="evenodd" />
              </svg>
              Input modified. Click &ldquo;Check Skill&rdquo; to re-evaluate.
            </span>
          )}
        </div>
      </div>

      {/* Right Column: Tabbed Output Panel */}
      <div className="lg:col-span-5 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden shadow-sm flex flex-col min-h-[500px]">
        {/* Tab Headers */}
        <div className="bg-zinc-50 dark:bg-zinc-950 border-b border-zinc-200 dark:border-zinc-800 px-2 pt-2 flex gap-1">
          <button
            onClick={() => setActiveTab('analysis')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors flex items-center gap-1.5 border-b-2 ${
              activeTab === 'analysis'
                ? 'bg-white dark:bg-zinc-900 border-blue-500 text-zinc-900 dark:text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-950 dark:hover:text-zinc-200'
            }`}
          >
            Analysis
            {hasDiagnosed && (
              <span className={`w-1.5 h-1.5 rounded-full ${
                overallVerdict === 'ready' ? 'bg-emerald-500' :
                overallVerdict === 'needs-work' ? 'bg-amber-500' : 'bg-red-500'
              }`} />
            )}
          </button>
          <button
            onClick={() => setActiveTab('guide')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors flex items-center gap-1.5 border-b-2 ${
              activeTab === 'guide'
                ? 'bg-white dark:bg-zinc-900 border-blue-500 text-zinc-900 dark:text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-950 dark:hover:text-zinc-200'
            }`}
          >
            Best Practices
          </button>
          <button
            onClick={() => setActiveTab('rules')}
            className={`px-4 py-2.5 text-xs font-semibold rounded-t-lg transition-colors flex items-center gap-1.5 border-b-2 ${
              activeTab === 'rules'
                ? 'bg-white dark:bg-zinc-900 border-blue-500 text-zinc-900 dark:text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-950 dark:hover:text-zinc-200'
            }`}
          >
            Rules Checked
          </button>
        </div>

        {/* Tab Body */}
        <div className="p-6 flex-1 overflow-y-auto">
          {activeTab === 'analysis' && renderAnalysis()}
          {activeTab === 'guide' && renderGuide()}
          {activeTab === 'rules' && renderRules()}
        </div>
      </div>
    </div>
  );
}
