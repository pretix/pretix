type FieldGroupDefinition = {
	identifier: string;
	entry_type: string;
	name: string;
	default_entries: FieldConfig[];
};

type Style = {
	identifier: string;
	name: string;
	fields: FieldGroupDefinition[];
};

type Variable = {
    label: string
};

type Styles = Record<string, Style>;
type Variables = Record<string, Variable>;
type VariableConfig = Record<string, Variables>;

type FieldEntry = {
    type: 'placeholder' | 'text';
    label: string; // TODO i18n
    content: string;
}

type FieldConfig = {
	entries: Array<FieldEntry>;
	overflow: string | null;
};

type LayoutData = {
	fields?: Record<string, FieldConfig>;
};

type Layout = {
	name?: string;
	style?: string;
	layout?: LayoutData;
};
