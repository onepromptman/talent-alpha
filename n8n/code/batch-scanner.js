
const config = $('Config').first().json;
if (typeof config.targetSectors !== 'string' || !config.targetSectors.trim() || !config.openRole?.title || !Array.isArray(config.openRole.functions)) throw new Error('Config needs targetSectors and an open role');
const batchIds = new Set();
const items = $input.all().map(i => i.json).filter(it => {
  if (it._emptyFeed) return false;
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
  'BEGIN_UNTRUSTED_ITEMS\n' + lines + '\nEND_UNTRUSTED_ITEMS';

return [{ json: { agentPrompt: prompt, itemsById: itemsById, count: items.length } }];
