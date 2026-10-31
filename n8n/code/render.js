const config = $('Config').first().json;
const OPEN_ROLE = config.openRole;
const COMPANY_NAME = config.companyProfile.split(' -- ')[0].trim();
const TIER_COLOR = { S: '#C8202E', A: '#1B3A2C', B: '#8A6B22', HELD: 'rgba(20,23,28,.45)' };

function elementSpan(doc, openStart) {
  const tagMatch = /<([a-zA-Z0-9]+)/.exec(doc.slice(openStart));
  const tag = tagMatch[1];
  const contentStart = doc.indexOf('>', openStart) + 1;
  const re = new RegExp('<' + tag + '\\b[^>]*>|</' + tag + '>', 'g');
  re.lastIndex = contentStart;
  let depth = 1, m;
  while ((m = re.exec(doc))) {
    depth += m[0].startsWith('</') ? -1 : 1;
    if (depth === 0) { return [contentStart, m.index]; }
  }
  throw new Error('unbalanced <' + tag + '>');
}

function fillSlot(doc, slot, content) {
  const re = new RegExp('<[a-zA-Z0-9]+[^>]*data-slot="' + slot + '"[^>]*>');
  const m = re.exec(doc);
  if (!m) { return doc; }
  const [a, b] = elementSpan(doc, m.index);
  return doc.slice(0, a) + content + doc.slice(b);
}

// Every value that reaches the card goes through esc(): feed text (company, location),
// model text (why, hook, edge, titles, bands, tier, wildcard) and Config text alike.
// It escapes quotes as well, so it is also safe inside an attribute value.
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function locLine(it) {
  return it.location + (it.employees_affected ? ' \u00b7 ' + it.employees_affected + ' affected' : '');
}

const allEvents = $input.all().map(i => i.json);
const eventsToRecord = allEvents.map(it => ({id: it.id}));
const items = allEvents.filter(it => !it.held);
const held = $input.all().map(i => i.json).filter(it => it.held);

let doc = TEMPLATE;
doc = fillSlot(doc, 'author', esc(config.author || 'Your name'));
doc = fillSlot(doc, 'run-date', new Date().toUTCString());
doc = fillSlot(doc, 'role-name', esc(OPEN_ROLE.title));
doc = fillSlot(doc, 'role-meta', esc(COMPANY_NAME + ' -- ' + OPEN_ROLE.location));

const counts = { S: 0, A: 0, B: 0, C: 0 };
items.forEach(it => { if (counts[it.tier] !== undefined) counts[it.tier]++; });
doc = fillSlot(doc, 'tier-counts', '<b style="color:var(--red)">' + counts.S + ' S</b> \u00b7 ' +
  '<b style="color:var(--green)">' + counts.A + ' A</b> \u00b7 ' +
  '<b style="color:var(--gold-dk)">' + counts.B + ' B</b> \u00b7 ' +
  '<b style="color:var(--gray)">' + counts.C + ' C</b>' +
  (held.length ? ' \u00b7 <b style="color:var(--gray)">' + held.length + ' held</b>' : ''));
doc = fillSlot(doc, 'run-id', (items.length + held.length) + ' signals scanned \u00b7 WARN: 3d; funding news: 7d');

const heldSummary = held.length
  ? held.length + ' item' + (held.length > 1 ? 's' : '') + ' held for review (judge disagreement) -- ' + held.map(h => h.company + ' (' + (h.hold_reason || 'disagreement') + ')').join('; ')
  : 'clean';

if (items.length === 0) {
  doc = fillSlot(doc, 'c-summary', esc(held.length
    ? 'No auto-cleared movements, but ' + heldSummary
    : 'No movements cleared the bar this run -- next scan tomorrow 06:00.'));
  doc = doc.replace(/<!-- HERO:START -->[\s\S]*?<!-- HERO:END -->/, '');
  doc = fillSlot(doc, 'foot-left', 'Talent Alpha · overnight brief');
  doc = fillSlot(doc, 'foot-right', 'Sources travel untrusted · review before outreach');
  verifyHtml(doc);
  return [{ json: { renderedHtml: doc, tierCounts: counts, itemCount: 0, heldCount: held.length, eventsToRecord } }];
}

const hero = items[0];
const rest = items.slice(1);

const heroChipColor = TIER_COLOR[hero.tier] || TIER_COLOR.HELD;
const heroChipHtml = hero.tier === 'S'
  ? '<span class="chipS">' + esc(hero.tier + ' \u00b7 ' + hero.event_type + ' ' + hero.event_age_label) + '</span>'
  : '<span class="chipS" style="background:none;border:1px solid ' + heroChipColor + ';color:' + heroChipColor + '">' + esc(hero.tier + ' \u00b7 ' + hero.event_type + ' ' + hero.event_age_label) + '</span>';
doc = doc.replace('<span class="chipS" data-slot="hero-tag">-</span>', heroChipHtml);
doc = fillSlot(doc, 'hero-company', esc(hero.company));
doc = fillSlot(doc, 'hero-loc', esc(locLine(hero)));
doc = fillSlot(doc, 'hero-titles', (hero.titles || []).map(t => '<span>' + esc(t) + '</span>').join(''));
doc = fillSlot(doc, 'hero-why', esc(hero.why));
doc = fillSlot(doc, 'hero-edge', esc(hero.edge || 'Not enough signal for a leverage read yet.'));
doc = fillSlot(doc, 'hero-hook', '"' + esc(hero.hook) + '"');
doc = fillSlot(doc, 'hero-source', sourceHtml(hero));
doc = doc.replace('data-bands="M,M,M,M,M,M" data-tier="S" data-size="150"',
  'data-bands="' + esc((hero.bands || []).join(',')) + '" data-tier="' + esc(hero.tier) + '" data-size="150"' +
  (hero.wildcard && hero.wildcard.fired ? ' data-wc="' + esc(hero.wildcard.axis_index) + '"' : ''));

const cardsHtml = rest.map((it) => {
  const wcAttr = it.wildcard && it.wildcard.fired ? ' data-wc="' + esc(it.wildcard.axis_index) + '"' : '';
  const bridgeChip = it.wildcard && it.wildcard.fired ? '<span class="bridge">\u25c6 ' + esc(it.wildcard.bridge) + '</span>' : '';
  return '<div class="card">' +
    '<div class="hex" data-bands="' + esc((it.bands || []).join(',')) + '" data-tier="' + esc(it.tier) + '" data-size="120"' + wcAttr + '></div>' +
    '<div><span class="tagA">' + esc(it.event_type + ' \u00b7 ' + it.event_age_label) + '</span>' + bridgeChip +
    '<div class="co">' + esc(it.tier + ' · ' + it.company) + '</div><div class="loc">' + esc(locLine(it)) + '</div>' +
    '<div class="titles">' + (it.titles || []).map(t => '<span>' + esc(t) + '</span>').join('') + '</div></div>' +
    '<div class="pillars3">' +
    '<div><div class="pl why">Why now</div><div class="ptext">' + esc(it.why) + '</div></div>' +
    '<div><div class="pl hook">The hook</div><div class="ptext">' + esc(it.hook) + '</div></div>' +
    '<div><div class="pl edge">The edge</div><div class="ptext dim">' + esc(it.edge || 'none yet') + '</div></div>' +
    '</div>' + sourceHtml(it) + '</div>';
}).join('');
doc = doc.replace('<!-- CARD:START -->\n<!-- CARD:END -->', '<!-- CARD:START -->' + cardsHtml + '<!-- CARD:END -->');

doc = fillSlot(doc, 'c-summary', esc(heldSummary));
doc = fillSlot(doc, 'foot-left', 'Talent Alpha \u00b7 overnight brief \u00b7 WARN + funding-distress categories');
doc = fillSlot(doc, 'foot-right', 'Sources travel untrusted \u00b7 nothing sends automatically');

verifyHtml(doc);
return [{ json: { renderedHtml: doc, tierCounts: counts, itemCount: items.length, heldCount: held.length, eventsToRecord } }];

function sourceHtml(it) {
  const name = esc(it.source_name || 'source');
  const url = String(it.source_url || '').trim();
  if (!/^https?:\/\/[^\s/]+/i.test(url)) return '<div class="srcline">Source: ' + name + ' (link withheld: not an http(s) URL)</div>';
  return '<div class="srcline">Source: <a href="' + esc(url) + '" rel="noopener noreferrer">' + name + '</a></div>';
}
function verifyHtml(doc) {
  if (/data-slot="[a-zA-Z0-9_-]+">-</.test(doc) || ['TBD','N/A','Data not available','NOT_FOUND'].some(s => doc.includes(s))) {
    throw new Error('Rendered card failed verification; events remain unseen');
  }
}
