const organizer_slug = document.body.getAttribute('data-organizer'),
	event_slug = document.body.getAttribute('data-event');

export async function get_questions() {
	return await (await fetch(`/api/v1/organizers/${organizer_slug}/events/${event_slug}/questions`)).json();
}

export async function get_items() {
	return await (await fetch(`/api/v1/organizers/${organizer_slug}/events/${event_slug}/items`)).json();
}
