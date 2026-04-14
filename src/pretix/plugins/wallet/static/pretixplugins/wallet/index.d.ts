type BaseFieldGroupDefinition = {
	type: string;
	identifier: string;
	name: string;
	required: boolean;
}

type FieldGroupDefinition = PlaceholderFieldGroupDefinition | PredefinedFieldGroup;

type PlaceholderFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: 'placeholder';
	content_type: FieldContentType;
	default_entries: FieldEntry[];
	labels: boolean;
	min_entries: number|null;
	max_entries: number|null;
}

type PredefinedFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: 'predefined';
}

type I18nString = string | Record<string, string>

type FieldContentType = 'text' | 'image';

type FieldEntry = {
    type: 'placeholder' | FieldContentType;
    label?: I18nString;
    content?: string;
}



type Style = {
	identifier: string;
	name: string;
	fieldgroups: FieldGroupDefinition[];
};

type Variable = {
    label: string
};

type Styles = Record<string, Style>;
type Variables = Record<string, Variable>;
type VariableConfig = Record<string, Variables>;



type PlaceholderFieldGroupConfig = {
	entries: Array<FieldEntry>;
	overflow: string | null;
};

type PredefinedFieldGroupConfig = {};

type FieldGroupConfig = PlaceholderFieldGroupConfig | PredefinedFieldGroupConfig;

type LayoutData = {
	fieldgroups: Record<string, FieldGroupConfig>;
};

type Layout = {
	name?: string;
	style?: string;
	layout?: LayoutData;
};

