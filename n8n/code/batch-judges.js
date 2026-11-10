
const config = $('Config').first().json;
const items = $input.all().map(i => i.json);
const itemsById = {};
items.forEach(it => { itemsById[it.id] = it; });

// Preserve the actual evidence so neither judge has to trust scanner reasoning.
const lines = items.map(it => JSON.stringify(it)).join('\n');

// Judges count ages in whole days to the run date (UTC), the date the card's count bar names.
const prompt = 'RUN_DATE: ' + new Date().toISOString().slice(0, 10) + '\n' +
  'COMPANY_PROFILE: ' + config.companyProfile + '\n' +
  'OPEN_ROLE: ' + JSON.stringify(config.openRole) + '\n' +
  'SOURCING_CRITERIA: ' + JSON.stringify(config.sourcingCriteria || {}) + '\n' +
  'COMPANY_FACTS: ' + JSON.stringify(config.companyFacts || {}) + '\n' +
  'BEGIN_UNTRUSTED_CANDIDATES\n' + lines + '\nEND_UNTRUSTED_CANDIDATES';

return [{ json: { judgePrompt: prompt, itemsById: itemsById } }];
