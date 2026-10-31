
const config = $('Config').first().json;
const items = $input.all().map(i => i.json);
const itemsById = {};
items.forEach(it => { itemsById[it.id] = it; });

// Preserve the actual evidence so neither judge has to trust scanner reasoning.
const lines = items.map(it => JSON.stringify(it)).join('\n');

const prompt = 'COMPANY_PROFILE: ' + config.companyProfile + '\n' +
  'OPEN_ROLE: ' + JSON.stringify(config.openRole) + '\n' +
  'BEGIN_UNTRUSTED_CANDIDATES\n' + lines + '\nEND_UNTRUSTED_CANDIDATES';

return [{ json: { judgePrompt: prompt, itemsById: itemsById } }];
