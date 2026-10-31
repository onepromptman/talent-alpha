
const raw = $input.first().json;
// Perplexity 'search' resource with simplify=true returns { id, results: [...] },
// each shaped { title, url, snippet, date, last_updated } -- confirmed via a live run.
const results = raw.results ?? raw.data;
if (raw.error || !Array.isArray(results)) throw new Error('Funding search failed or returned an invalid shape');
if (!results.length) return [{json: {_emptyFeed: 'funding', event_id: '__talent_alpha_empty_funding'}}];

function hashUrl(url) {
  // Stable URL hash for source-ID dedupe; different articles remain different events.
  let h = 5381;
  for (let i = 0; i < url.length; i++) { h = ((h * 33) ^ url.charCodeAt(i)) >>> 0; }
  return h.toString(36);
}

const output = results.map((r) => {
  const title = r.title || r.name || '';
  const url = r.url || r.link || '';
  const snippet = r.snippet || r.content || r.text || r.excerpt || '';
  const publishedAt = r.date || r.published_date || r.last_updated || r.publishedDate || null;
  return {
    json: {
      event_id: 'fund-' + hashUrl(url),
      published_at: publishedAt,
      title: title,
      snippet: snippet,
      source_name: 'Perplexity Search',
      source_url: url,
      company: '',
      location: '',
      event_type: 'funding_distress',
      employees_affected: null
    }
  };
}).filter((it) => it.json.title && it.json.source_url && it.json.snippet && it.json.snippet.length > 40);

if (!output.length) throw new Error("Funding search returned results but none were usable");
return output;
