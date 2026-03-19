const organizer_slug = document.body.getAttribute('data-organizer'),
	event_slug = document.body.getAttribute('data-event');

export async function get_datafields() {
	return await (await fetch(`/api/v1/organizers/${organizer_slug}/events/${event_slug}/datafields/`)).json();
}

export async function get_questionnaires() {
	return await (await fetch(`/api/v1/organizers/${organizer_slug}/events/${event_slug}/questionnaires/`)).json();
}

export async function get_items() {
	return await (await fetch(`/api/v1/organizers/${organizer_slug}/events/${event_slug}/items/`)).json();
}
