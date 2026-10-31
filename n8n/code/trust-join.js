const output = $input.first().json.output;
if (!output || !Array.isArray(output.opportunities)) throw new Error('Scanner did not return a valid shortlist');
const trustedMap = $('Batch For Scanner Agent').first().json.itemsById;
const seen = new Set();
function extracted(base, value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  const words = text => (String(text).toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []).join(' ');
  const needle = words(value);
  const evidence = ' ' + words((base.title || '') + ' ' + (base.snippet || '')) + ' ';
  return needle && evidence.includes(' ' + needle + ' ') ? value.trim() : '';
}
const result = [];
for (const o of output.opportunities) {
  const base = trustedMap[o.id];
  if (!base) throw new Error('Scanner returned an unknown event ID: ' + o.id);
  if (seen.has(o.id)) throw new Error('Scanner returned a duplicate event ID: ' + o.id);
  seen.add(o.id);
  const company = base.company || (base.event_type === 'funding_distress' ? extracted(base, o.company) : '');
  if (!company) throw new Error('Company extraction is not supported by source text: ' + o.id);
  if (!/^https?:\/\/[^\s/]+/i.test(base.source_url || '') || !base.source_name) throw new Error('Event has no checkable source: ' + o.id);
  const stamp = Date.parse(base.published_at);
  if (!Number.isFinite(stamp) || stamp > Date.now() + 86400000) throw new Error('Invalid event date: ' + o.id);
  result.push({json: {
    id: o.id, company, event_type: base.event_type, functions: o.functions || [],
    location: base.location || extracted(base, o.location), employees_affected: base.employees_affected ?? null,
    published_at: base.published_at, score: o.score, why: o.why,
    source_name: base.source_name, source_url: base.source_url,
    title: base.title || '', snippet: base.snippet || ''
  }});
}
return result;
