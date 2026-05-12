
export type ApiListResponse<T> = {
	count: number,
	next: string | null,
	previous: string | null,
	results: T[],
};

// from webcheckin/i18n.ts
export type I18nString = string | Record<string, string> | null | undefined;

export type Datafield = {
	id: number,
	// question: I18nString,
	type: string,
	required: boolean,
	//items: number[],
	options: any[],
	// position: number,
	ask_during_checkin: boolean,
	show_during_checkin: boolean,
	identifier: string,
	// dependency_question: string | null,
	// dependency_values	[]
	hidden: boolean,
	// dependency_value	null
	print_on_invoice: boolean,
	// help_text: I18nString,
	valid_number_min: null | number,
	valid_number_max: null | number,
	valid_date_min: null | string,
	valid_date_max: null | string,
	valid_datetime_min: null | string,
	valid_datetime_max: null | string,
	valid_string_length_max: null | number,
	valid_file_portrait: boolean,
	internal_name: string,
};

export type Questionnaire = {
	id: number,
	internal_name: string,
	items: number[],
	position: number,
	all_sales_channels: boolean,
	limit_sales_channels: string[],
	children: QuestionnaireChild[],
};

export type QuestionnaireChild = {
	question: string | number,
	required: boolean,
	label: I18nString,
	help_text: I18nString,
	dependency_question: number | null,
	dependency_values: null | string[],
};

export type Item = {
	id: number,
	category: number,
	name: I18nString,
	internal_name: string | null,
};
