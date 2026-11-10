const rank = {S: 3, A: 2, B: 1, C: 0};
const tiers = ['C', 'B', 'A', 'S'];
const axes = ['openness', 'role_fit', 'product_fit', 'region_fit', 'size_fit', 'stage_fit'];
const trusted = $('Trust-Boundary Join').all().map(i => i.json);
const config = $('Config').first().json;
function index(rows, label) {
  if (!Array.isArray(rows)) throw new Error(label + ' did not return a verdict array');
  const map = new Map();
  for (const row of rows) {
    if (!row || typeof row.id !== 'string' || !row.id || map.has(row.id)) throw new Error(label + ' has missing or duplicate IDs');
    map.set(row.id, row);
  }
  return map;
}
const sources = index(trusted, 'trusted batch');
const advocate = index(modelOutput($('Judge Advocate').first().json).verdicts, 'Advocate');
const skeptic = index(modelOutput($('Judge Skeptic').first().json).verdicts, 'Skeptic');
for (const [label, verdicts] of [['Advocate', advocate], ['Skeptic', skeptic]]) {
  if (verdicts.size !== sources.size || [...sources.keys()].some(id => !verdicts.has(id))) {
    throw new Error(label + ' must cover every trusted event exactly once');
  }
  for (const v of verdicts.values()) {
    if (!Object.hasOwn(rank, v.tier) || axes.some(a => !['H','M','L'].includes(v[a]))) throw new Error(label + ' returned an invalid tier or axis');
    if (['why','hook','edge'].some(k => typeof v[k] !== 'string') || !v.why.trim()) throw new Error(label + ' returned invalid prose fields');
    if (!Array.isArray(v.titles) || v.titles.some(t => typeof t !== 'string')) throw new Error(label + ' returned invalid titles');
    const wc = v.wildcard;
    if (!wc || typeof wc.fired !== 'boolean' || !Number.isInteger(wc.axis_index) || wc.axis_index < -1 || wc.axis_index > 5 || typeof wc.bridge !== 'string') throw new Error(label + ' returned an invalid wildcard');
    if (wc.fired && (wc.axis_index < 0 || !wc.bridge.trim())) throw new Error(label + ' returned an unsupported wildcard');
  }
}
// Numeric claims must occur in the source or the user's profile. Percentages may
// be derived, so only explicit money and multi-digit counts are hard failures.
function numbers(text) {
  const found = new Set();
  const patterns = [/\$\s?\d[\d,]*(?:\.\d+)?\s?[KkMm]?/g, /(?<![\d.$])\d{2,3}(?:,\d{3})+(?![\d%])|(?<![\d.$,])\d{2,}(?![\d%,])/g];
  for (let i = 0; i < patterns.length; i++) {
    for (const match of String(text).matchAll(patterns[i])) {
      let token = match[0].trim();
      if (i === 1 && /^(19|20)\d{2}$/.test(token)) continue;
      const factor = /k$/i.test(token) ? 1000 : /m$/i.test(token) ? 1000000 : 1;
      token = token.replace(/[$,\sKkMm]/g, '');
      found.add(String(Number(token) * factor));
    }
  }
  return found;
}
const finals = [];
for (const t of trusted) {
  const a = advocate.get(t.id), s = skeptic.get(t.id);
  const evidence = [t.title, t.snippet, t.employees_affected, String(t.published_at).slice(0,10), config.companyProfile].filter(v => v !== undefined && v !== null).join(' ');
  const allowed = numbers(evidence);
  for (const claim of numbers([a.why, a.hook, a.edge, ...a.titles].join(' '))) {
    if (!allowed.has(claim)) throw new Error('Unsupported numeric claim for ' + t.id + ': ' + claim);
  }
  if (!String(config.companyProfile || '').trim() && a.edge.trim()) throw new Error('An edge requires a saved company profile');
  // Fit axes are scores, not card text; the plugin build rejects the same thing.
  if (/\b[A-Za-z]+_fit\b/.test([a.why, a.hook, a.edge].join(' '))) throw new Error('Card text names a fit axis for ' + t.id);
  // There is no model repair lap in n8n. Missing structured facts are neutral,
  // even if a judge inferred a size or stage from the pitch text.
  for (const [fact, axis] of [['size', 'size_fit'], ['stage', 'stage_fit']]) {
    if (!String(config.companyFacts?.[fact] || '').trim()) {
      a[axis] = 'M'; s[axis] = 'M';
    }
  }
  const age = Math.max(0, Math.floor(Date.now() / 86400000) - Math.floor(Date.parse(t.published_at) / 86400000));
  if (!Number.isFinite(age)) throw new Error('Invalid date for ' + t.id);
  const blended = Math.round((rank[a.tier] + rank[s.tier]) / 2);
  finals.push({json: {
    id: t.id, company: t.company, location: t.location, employees_affected: t.employees_affected ?? null,
    event_type: t.event_type, published_at: t.published_at, event_age_label: age === 0 ? 'today' : age + 'd ago', age_days: age,
    titles: a.titles, tier: tiers[blended], _rank: blended, _disagree: Math.abs(rank[a.tier] - rank[s.tier]) >= 3,
    bands: axes.map(axis => a[axis]), wildcard: a.wildcard, why: a.why, hook: a.hook, edge: a.edge,
    held: false, hold_reason: '', source_name: t.source_name, source_url: t.source_url
  }});
}
finals.sort((a,b) => b.json._rank - a.json._rank || a.json.age_days - b.json.age_days);
const MAX_SHOWN = config.maxShown ?? 10;
let shown = 0;
finals.forEach(f => {
  if (shown >= MAX_SHOWN || f.json._disagree) {
    f.json.held = true; f.json.tier = 'HELD';
    f.json.hold_reason = f.json._disagree ? 'judges disagreed sharply' : 'beyond the top ' + MAX_SHOWN + ' this run';
  }
  if (!f.json.held) shown++;
  delete f.json._rank; delete f.json._disagree;
});
return finals;
