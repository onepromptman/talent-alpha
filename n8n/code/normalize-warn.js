const response = $input.first().json;
if (!Array.isArray(response.records) || response.error) {
  throw new Error('WARN response is invalid; this is a source failure, not a quiet day');
}
const rows = response.records;
if (!rows.length) return [{json: {_emptyFeed: 'warn', event_id: '__talent_alpha_empty_warn'}}];
const output = [];
for (const r of rows) {
  const company = String(r.company_name || r.display_name || '').trim();
  if (!company || /\.pdf|\(pdf\)/i.test(company)) continue;
  if (r.id === undefined || r.id === null) throw new Error('WARN record has no ID');
  const date = r.notice_date || r.effective_date;
  if (!date || !Number.isFinite(Date.parse(date)) || Date.parse(date) > Date.now() + 86400000) {
    throw new Error('WARN record has an invalid publication date');
  }
  if (!/^https?:\/\/[^\s/]+/i.test(r.source_url || '')) throw new Error('WARN record has no checkable source URL');
  const affected = r.employees_affected ?? null;
  if (affected !== null && (!Number.isInteger(affected) || affected < 0)) throw new Error('WARN headcount is invalid');
  const location = [r.city, r.state].filter(Boolean).join(', ');
  const eventType = /closure/i.test(r.layoff_type || '') ? 'shutdown' : 'layoff';
  output.push({json: {
    event_id: 'warn-' + r.id, published_at: date,
    title: company + ' WARN ' + eventType + (affected ? ' -- ' + affected + ' affected' : ''),
    snippet: [location, r.industry].filter(Boolean).join(' -- ') + (affected ? ' -- ' + affected + ' employees affected' : ''),
    source_name: 'WARN Firehose', source_url: r.source_url, company, location,
    event_type: eventType, employees_affected: affected
  }});
}
if (!output.length) throw new Error('WARN returned records but none were usable; inspect the response');
return output;
