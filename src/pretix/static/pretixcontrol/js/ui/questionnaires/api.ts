const organizer_slug = document.body.getAttribute('data-organizer'),
	event_slug = document.body.getAttribute('data-event');

async function api_get(resource) {
	return await $.getJSON(`/api/v1/${resource}?_nocache=${+new Date()}`);
}

async function api_json_request(resource, method, json_body) {
	return await (await fetch(`/api/v1/${resource}`, {
		body: JSON.stringify(json_body),
		method: method,
		headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": $('[name=csrfmiddlewaretoken]').val(),
		},
	})).json();
}

export async function get_datafields() {
	return await api_get(`organizers/${organizer_slug}/events/${event_slug}/datafields/`);
}

export async function get_questionnaires() {
	return await api_get(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`);
}

export async function update_questionnaire(id, data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/${id}/`, 'PATCH', data);
}

export async function create_questionnaire(data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`, 'POST', data);
}

export async function get_items() {
	return await api_get(`organizers/${organizer_slug}/events/${event_slug}/items/`);
}

function get_json_script_value(id) {
	return JSON.parse(document.getElementById(id).innerText);
}

export function get_event_locales() {
	return get_json_script_value('event_locales');
}
