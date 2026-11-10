// CONFIG_SCHEMA is injected from the plugin's schema by the export builder.
function validateConfig(config) {
  function check(value, schema, path) {
    const types = {object: value !== null && typeof value === 'object' && !Array.isArray(value),
      array: Array.isArray(value), string: typeof value === 'string',
      integer: Number.isInteger(value), boolean: typeof value === 'boolean'};
    if (schema.type && !types[schema.type]) throw new Error('Config: ' + path + ' must be ' + schema.type);
    if (schema.enum && !schema.enum.includes(value)) throw new Error('Config: invalid ' + path);
    if (schema.type === 'object') {
      for (const key of schema.required || []) if (!(key in value)) throw new Error('Config: missing ' + path + '.' + key);
      for (const [key, child] of Object.entries(value)) {
        const field = schema.properties?.[key];
        if (!field && schema.additionalProperties === false) throw new Error('Config: unknown ' + path + '.' + key);
        if (field) check(child, field, path + '.' + key);
      }
    }
    if (schema.type === 'array') {
      if (schema.minItems !== undefined && value.length < schema.minItems) throw new Error('Config: empty ' + path);
      value.forEach((item, i) => check(item, schema.items, path + '[' + i + ']'));
    }
    if (schema.type === 'integer' && (value < schema.minimum || value > schema.maximum)) throw new Error('Config: out of range ' + path);
  }
  check(config, CONFIG_SCHEMA, 'config');
  if (![config.targetSectors, config.openRole.id, config.openRole.title, ...config.openRole.functions].every(s => s.trim())) {
    throw new Error('Config needs nonempty targetSectors and open role id, title and functions');
  }
  const criteria = config.sourcingCriteria || {};
  for (const key of ['skills', 'eligibleLocations', 'priorityTriggers', 'excludeCompanies']) {
    if ((criteria[key] || []).some(s => !s.trim())) throw new Error('Config: blank entry in ' + key);
  }
  if (config.includeFundingDistress === false && criteria.eventTypes?.every(t => t === 'funding_distress')) {
    throw new Error('Config: no enabled event types');
  }
  return config;
}
