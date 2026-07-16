// Fully client-side SKILL.md linter. No network, no dependencies. Rule ids
// are stable ("SD01"...) so findings can be referenced/tested individually.

export interface Finding {
  id: string;
  severity: 'error' | 'warn' | 'info';
  title: string;
  detail: string;
}

export interface ParsedSkill {
  hasFrontmatter: boolean;
  frontmatter: Record<string, string>;
  body: string;
}

const TOP_LEVEL_KEY_RE = /^([A-Za-z0-9_-]+):(?:[ \t](.*))?$/;

// Deliberately minimal: no YAML library. Only top-level "key: value" lines
// are parsed, plus simple continuation (a ">"/"|" block-scalar marker, or a
// value simply continued on following more-indented lines, concatenated
// with spaces). Anything else inside the fence is ignored silently.
export function parseSkillMd(text: string): ParsedSkill {
  const normalized = text.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');

  if (lines[0] === undefined || lines[0].trim() !== '---') {
    return { hasFrontmatter: false, frontmatter: {}, body: normalized };
  }

  let closeIdx = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      closeIdx = i;
      break;
    }
  }

  if (closeIdx === -1) {
    return { hasFrontmatter: false, frontmatter: {}, body: normalized };
  }

  const frontmatterLines = lines.slice(1, closeIdx);
  const body = lines.slice(closeIdx + 1).join('\n');

  const frontmatter: Record<string, string> = {};
  let currentKey: string | null = null;

  for (const rawLine of frontmatterLines) {
    if (rawLine.trim() === '') continue;

    const isIndented = /^[ \t]/.test(rawLine);
    if (isIndented) {
      if (currentKey) {
        const cont = rawLine.trim();
        frontmatter[currentKey] = frontmatter[currentKey]
          ? `${frontmatter[currentKey]} ${cont}`
          : cont;
      }
      continue;
    }

    const match = TOP_LEVEL_KEY_RE.exec(rawLine);
    if (!match) {
      currentKey = null;
      continue;
    }

    const key = match[1];
    const value = (match[2] ?? '').trim();
    frontmatter[key] = value === '>' || value === '|' ? '' : value;
    currentKey = key;
  }

  return { hasFrontmatter: true, frontmatter, body };
}

// round(chars / 4) - keep in parity with kitchen/nutrition.py's estimate.
export function estimateTokens(text: string): number {
  return Math.round(text.length / 4);
}

const KEBAB_CASE_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const TRIGGER_PHRASE_RE = /use when|use this when|use it when|use for|use if|trigger/i;
// Two separate checks rather than one `^i\s|\si can\s|\si will\s` regex: the
// leading `^` there only bound to the first alternative, which is correct
// (start-of-string vs. contains) but reads as a mistake - CodeQL flags this
// shape as "missing regular expression anchor" since anchored and
// unanchored alternatives are easy to misread as uniformly anchored.
const STARTS_WITH_I_RE = /^i\s/i;
const CONTAINS_FIRST_PERSON_VERB_RE = /\si can\s|\si will\s/i;
function isFirstPerson(description: string): boolean {
  return STARTS_WITH_I_RE.test(description) || CONTAINS_FIRST_PERSON_VERB_RE.test(description);
}
const OVERRIDE_PHRASE_RE = /ignore previous instructions|ignore all previous|disregard the above/i;

export function diagnose(text: string): Finding[] {
  const findings: Finding[] = [];
  const { hasFrontmatter, frontmatter, body } = parseSkillMd(text);

  if (!hasFrontmatter) {
    findings.push({
      id: 'SD01',
      severity: 'error',
      title: 'Missing frontmatter block',
      detail: 'SKILL.md must start with a "---" line and close the frontmatter with another "---" line before the body.',
    });
  }

  const name = frontmatter.name;
  if (!name) {
    findings.push({
      id: 'SD02',
      severity: 'error',
      title: 'Missing "name" field',
      detail: 'Add a name: field to the frontmatter - it identifies the skill to the harness.',
    });
  } else if (!KEBAB_CASE_RE.test(name) || name.length > 64) {
    findings.push({
      id: 'SD03',
      severity: 'warn',
      title: 'Name is not kebab-case, or too long',
      detail: 'Use lowercase letters, digits, and single hyphens (e.g. "pdf-form-filler"), and keep it to 64 characters or fewer.',
    });
  }

  const description = frontmatter.description;
  if (!description) {
    findings.push({
      id: 'SD04',
      severity: 'error',
      title: 'Missing "description" field',
      detail: 'Add a description: field - this is what the harness matches against to decide when to load the skill.',
    });
  } else {
    if (description.length < 80) {
      findings.push({
        id: 'SD05',
        severity: 'warn',
        title: 'Description is too short',
        detail: 'Descriptions under 80 characters are often too thin for the harness to match reliably; describe what the skill does and when to use it.',
      });
    }
    if (description.length > 1024) {
      findings.push({
        id: 'SD06',
        severity: 'warn',
        title: 'Description is too long',
        detail: 'Descriptions over 1024 characters can crowd out other context in the harness prompt; trim it down to the essentials.',
      });
    }
    if (!TRIGGER_PHRASE_RE.test(description)) {
      findings.push({
        id: 'SD07',
        severity: 'warn',
        title: 'Description lacks trigger phrasing',
        detail: 'Add a phrase like "Use this when..." or "Use for..." - this is the single most common cause of a skill never firing.',
      });
    }
    if (isFirstPerson(description)) {
      findings.push({
        id: 'SD08',
        severity: 'warn',
        title: 'Description is written in first person',
        detail: 'Describe the skill in third person (e.g. "Creates reports...") rather than "I create reports..." or "I can...".',
      });
    }
  }

  if (estimateTokens(body) > 5000) {
    findings.push({
      id: 'SD09',
      severity: 'info',
      title: 'Body is large',
      detail: 'This body is over ~5000 tokens; consider splitting detail into referenced files for progressive disclosure.',
    });
  }

  if (OVERRIDE_PHRASE_RE.test(body)) {
    findings.push({
      id: 'SD10',
      severity: 'warn',
      title: 'Body contains override phrasing',
      detail: 'Phrasing like "ignore previous instructions" reads as a prompt-injection attempt and will likely fail review.',
    });
  }

  if (body.trim() === '') {
    findings.push({
      id: 'SD11',
      severity: 'info',
      title: 'Body is empty',
      detail: 'This is a frontmatter-only skill with no body content beyond the description.',
    });
  }

  return findings;
}

const TRIGGER_SENTENCE_SPLIT_RE = /(?<=[.!?])\s+/;

// Mirrors kitchen/nutrition.py's extract_trigger() so the Doctor's mini
// preview reads the same way the catalog's "Loads when: ..." line does.
export function extractTrigger(description: string): string {
  const trimmed = description.trim();
  if (!trimmed) return '';

  const sentences = trimmed
    .split(TRIGGER_SENTENCE_SPLIT_RE)
    .map((s) => s.trim())
    .filter(Boolean);
  if (sentences.length === 0) return '';

  const trigger = sentences.find((s) => TRIGGER_PHRASE_RE.test(s)) ?? sentences[0];
  if (trigger.length > 200) {
    return `${trigger.slice(0, 199)}…`;
  }
  return trigger;
}

export function verdict(findings: Finding[]): 'ready' | 'needs-work' | 'blocked' {
  const hasError = findings.some((f) => f.severity === 'error');
  if (hasError) return 'blocked';

  const warnCount = findings.filter((f) => f.severity === 'warn').length;
  if (warnCount >= 2) return 'needs-work';

  return 'ready';
}
