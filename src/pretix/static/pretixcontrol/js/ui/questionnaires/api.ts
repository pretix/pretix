import {ApiListResponse, Datafield, Questionnaire, Item, Category, SalesChannel} from './model'
import { ProgressBar } from "./ProgressBar";
import {fromJsonScript} from "./helper";

const organizer_slug = document.body.getAttribute('data-organizer'),
	event_slug = document.body.getAttribute('data-event')

async function api_get(resource) {
	return await $.getJSON(`/api/v1/${resource}?_nocache=${+new Date()}`)
}

async function api_get_all<T>(resource): Promise<T[]> {
	let next = `/api/v1/${resource}?_nocache=${+new Date()}`
	const result: T[] = [];
	while (next) {
		const response: ApiListResponse<T> = await $.getJSON(next)
		result.push(...response.results)
		next = response.next
		console.log('api_get_all: ' + resource, next, response, result)
	}
	return result
}

class APIError extends Error {
	api_error: string;
	constructor(json) {
		super('' + Object.values(json)[0]);
		this.api_error = json;
	}
}
async function api_json_request(resource, method, json_body) {
	const response = await fetch(`/api/v1/${resource}`, {
		body: JSON.stringify(json_body),
		method: method,
		headers: {
			'Content-Type': 'application/json',
			'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val() as string,
		},
	});
	if (response.status === 204)
		return {}
	else if (response.status >= 400)
		throw new APIError(await response.json());
	else
		return await response.json()
}

export async function getDatafields(container_type) {
	using pb = ProgressBar.show('loading data fields')
	return await api_get_all<Datafield>(`organizers/${organizer_slug}/events/${event_slug}/datafields/?container_type=${container_type}&`);
}

export async function getQuestionnaires() {
	using pb = ProgressBar.show('loading questionnaires')
	return await api_get_all<Questionnaire>(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`);
}

export async function updateQuestionnaire(id, data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/${id}/`, 'PATCH', data);
}

export async function createQuestionnaire(data) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/`, 'POST', data);
}

export async function deleteQuestionnaire(id) {
	return await api_json_request(`organizers/${organizer_slug}/events/${event_slug}/questionnaires/${id}/`, 'DELETE', {});
}

export async function getItems() {
	using pb = ProgressBar.show('loading product list')
	return await api_get_all<Item>(`organizers/${organizer_slug}/events/${event_slug}/items/`);
}

export async function getCategories() {
	using pb = ProgressBar.show('loading category list')
	return await api_get_all<Category>(`organizers/${organizer_slug}/events/${event_slug}/categories/`);
}

export async function getSalesChannels() {
	return await api_get_all<SalesChannel>(`organizers/${organizer_slug}/saleschannels/`);
}

export function getEventLocales() {
	return fromJsonScript('event_locales');
}

export function getDatafieldViewUrl(datafield_id) {
	return fromJsonScript('datafield_view_url').replace('/0/', `/${datafield_id}/`);
}
export function getDatafieldEditUrl(datafield_id) {
	return fromJsonScript('datafield_edit_url').replace('/0/', `/${datafield_id}/`) + '?notify_parent=true&';
}

export function getDatafieldCreateUrl(container_type) {
	return fromJsonScript('datafield_create_url') + '?notify_parent=true&container_type=' + container_type;
}
