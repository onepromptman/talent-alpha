
const config = $('Config').first().json;
validateConfig(config);
const role = config.openRole;
if (typeof config.targetSectors !== 'string' || !config.targetSectors.trim() ||
    typeof config.companyProfile !== 'string' || typeof role?.title !== 'string' ||
    !role.title.trim() || typeof role.location !== 'string' ||
    !Array.isArray(role.functions) || !role.functions.length ||
    role.functions.some(f => typeof f !== 'string' || !f.trim())) {
  throw new Error('Config needs targetSectors, companyProfile (empty is allowed), and an open role with title, location and nonempty functions');
}
const batchIds = new Set();
const items = $input.all().map(i => i.json).filter(it => {
  if (it._emptyFeed) return false;
  const criteria = config.sourcingCriteria || {};
  if (config.includeFundingDistress === false && it.event_type === 'funding_distress') return false;
  if (criteria.eventTypes && !criteria.eventTypes.includes(it.event_type)) return false;
  if ((criteria.excludeCompanies || []).some(c => c.trim().toLowerCase() === String(it.company || '').trim().toLowerCase())) return false;
  const stamp = Date.parse(it.published_at);
  if (!Number.isFinite(stamp) || stamp > Date.now() + 86400000) throw new Error('Invalid event date before scanner');
  const limit = WINDOW_DAYS?.[it.event_type];
  if (Number.isInteger(limit) && Math.floor(Date.now() / 86400000) - Math.floor(stamp / 86400000) > limit) return false;
  if (!it.event_id) throw new Error('Event has no event_id');
  if (batchIds.has(it.event_id)) return false;
  batchIds.add(it.event_id); return true;
});
if (!items.length) return [];
const itemsById = {};
items.forEach(it => { itemsById[it.event_id] = it; });

const lines = items.map(it =>
  it.event_id + ' | ' + it.published_at + ' | ' + it.title + ' | ' + it.snippet + ' | ' + it.source_name
).join('\n');

const prompt = 'RUN_TIMESTAMP: ' + new Date().toISOString() + '\n' +
  'COMPANY_PROFILE: ' + config.companyProfile + '\n' +
  'OPEN_ROLE: ' + JSON.stringify(config.openRole) + '\n' +
  'SOURCING_CRITERIA: ' + JSON.stringify(config.sourcingCriteria || {}) + '\n' +
  'COMPANY_FACTS: ' + JSON.stringify(config.companyFacts || {}) + '\n' +
  'BEGIN_UNTRUSTED_ITEMS\n' + lines + '\nEND_UNTRUSTED_ITEMS';

return [{ json: { agentPrompt: prompt, itemsById: itemsById, count: items.length } }];
