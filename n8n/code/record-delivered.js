const delivery = $input.first().json;
if (!delivery || typeof delivery.id !== 'string' || !delivery.id) {
  throw new Error('Gmail did not confirm delivery; events remain unseen for retry');
}
const events = $('Render Scanner Report').first().json.eventsToRecord;
if (!Array.isArray(events)) throw new Error('Rendered digest has no event IDs to record');
return events.map(event => ({json: {id: event.id, delivery_message_id: delivery.id}}));
