// The builder shares this adapter between scanner and judge consumers.
// Basic LLM Chain returns parsed objects directly; older exports used output.
function modelOutput(data) {
  let output = data?.output ?? data?.text ?? data;
  if (typeof output === 'string') {
    try { output = JSON.parse(output); }
    catch { throw new Error('Model returned invalid JSON; no card was created'); }
  }
  if (!output || typeof output !== 'object' || Array.isArray(output)) {
    throw new Error('Model did not return a structured object; no card was created');
  }
  return output;
}
