import {ApiListResponse, Datafield, Questionnaire, Item} from "./model";

const organizer_slug = document.body.getAttribute('data-organizer'),
	event_slug = document.body.getAttribute('data-event');

async function api_get(resource) {
	return await $.getJSON(`/api/v1/${resource}?_nocache=${+new Date()}`);
}

async function api_get_all<T>(resource): Promise<T[]> {
	let next = `/api/v1/${resource}?_nocache=${+new Date()}`;
	const result: T[] = [];
	while (next) {
		const response: ApiListResponse<T> = await $.getJSON(next);
		result.push(...response.results);
		next = response.next;
		console.log('api_get_all: '+ resource, next, response, result)
	}
	return result;
}

async function api_json_request(resource, method, json_body) {
	return await (await fetch(`/api/v1/${resource}`, {
		body: JSON.stringify(json_body),
		method: method,
		headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": $('[name=csrfmiddlewaretoken]').val() as string,
		},
	})).json();
}

export async function getDatafields() {
	return await api_get_all<Datafield>(`organizers/${organizer_slug}/events/${event_slug}/datafields/`);
}

export async function getQuestionnaires() {
	return await api_get_all<Questionnaire>(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`);
}

export async function updateQuestionnaire(id, data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/${id}/`, 'PATCH', data);
}

export async function createQuestionnaire(data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`, 'POST', data);
}

export async function getItems() {
	return await api_get_all<Item>(`organizers/${organizer_slug}/events/${event_slug}/items/`);
}

export async function getCategories() {
	return await api_get_all<Item>(`organizers/${organizer_slug}/events/${event_slug}/categories/`);
}

function get_json_script_value(id) {
	return JSON.parse(document.getElementById(id).innerText);
}

export function getEventLocales() {
	return get_json_script_value('event_locales');
}

export function getDatafieldEditUrl(datafield_id) {
	return get_json_script_value('datafield_edit_url').replace('/0/', `/${datafield_id}/`);
}
