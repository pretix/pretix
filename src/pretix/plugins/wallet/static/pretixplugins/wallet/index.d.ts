type Platform = {
	identifier: string;
	name: string;
	styles: Styles;
};

type Style = {
	identifier: string;
	name: string;
	fieldgroups: FieldGroupDefinition[];
	settings: Setting[];
	preview_renderer: string;
	preview_data: Record<string, string>;
};

type Placeholder = {
	label: string;
	sample: string;
	required_context: string[];
};

type Styles = Record<string, Style>;
type Placeholders = Record<string, Placeholder>;
type PlaceholderConfig = Record<string, Placeholders>;
type Platforms = Platform[];

type BaseFieldGroupDefinition = {
	type: FieldGroupType;
	identifier: string;
	name: string;
	description: string;
	required: boolean;
};

type FieldGroupDefinition =
	| PlaceholderFieldGroupDefinition
	| PredefinedFieldGroupDefinition;

type FieldGroupDisplay = "plain" | "with_label";
type FieldGroupType = "placeholder" | "predefined";
type FieldContentType = "text" | "image";

type PlaceholderFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: "placeholder";
	content_type: FieldContentType;
	default_entries: FieldEntry[];
	min_entries: number | null;
	max_entries: number | null;
	context_args: string[];
};

type PredefinedFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: "predefined";
	default_active: boolean;
};

type LocalizableString = null | string | Record<string, string>;

type PlaceholderFieldEntry = {
	type: "placeholder";
	label: LocalizableString;
	content?: string;
};

type CustomFieldEntry = {
	type: "custom";
	label?: LocalizableString;
	content?: LocalizableString;
};

type FieldEntry = PlaceholderFieldEntry | CustomFieldEntry;

type Setting = {
	identifier: string;
	label: string;
	type: "text" | "image" | "color" | "float" | "bool";
	required: boolean;
	help_text: string;
	default: string;
};

type PlaceholderFieldGroupConfig = {
	entries: Array<FieldEntry>;
	overflow: string | null;
};

type PredefinedFieldGroupConfig = {
	active: boolean;
};

type FieldGroupConfig =
	| PlaceholderFieldGroupConfig
	| PredefinedFieldGroupConfig;

type LayoutData = {
	fieldgroups?: Record<string, FieldGroupConfig>;
	settings?: Record<string, any>;
};


type PlatformLayout = {
	style: string;
	fieldgroups: {};
	settings: {};
	file_settings: Record<string, WalletFile>;
};
type ServerSideFile = { url: string; name: string };
type ClientSideFile = { file: File | null; identifier?: string };
type WalletFile = ServerSideFile | ClientSideFile;
