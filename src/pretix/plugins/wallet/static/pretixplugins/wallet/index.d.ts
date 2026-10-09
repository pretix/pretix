type Platform = {
	identifier: string;
	name: string;
	styles: Styles;
};

type Style = {
	identifier: string;
	name: string;
	fieldgroups: FieldGroupDefinition[];
	preview_layout: PreviewLayout[];
	settings: Setting[];
};

type Variable = {
	label: string;
	sample: string;
	required_context: string[];
};

type Styles = Record<string, Style>;
type Variables = Record<string, Variable>;
type VariableConfig = Record<string, Variables>;
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

type FieldGroupDisplay = "plain" | "with_label" | "code";
type FieldGroupType = "placeholder" | "predefined";
type FieldContentType = "text" | "image";

type PlaceholderFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: "placeholder";
	content_type: FieldContentType;
	default_entries: FieldEntry[];
	display: FieldGroupDisplay;
	min_entries: number | null;
	max_entries: number | null;
	context_args: string[];
};

type PredefinedFieldGroupDefinition = BaseFieldGroupDefinition & {
	type: "predefined";
};

type LocalizableString = null | string | Record<string, string>;


type PlaceholderFieldEntry = {
	type: "placeholder";
	label: LocalizableString;
	content: string;
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
	type: "text" | "image" | "color" | "float";
	required: boolean;
	help_text: string;
	default: string
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

type PreviewLayout = {"style": Record<string, string | {settting: string}>, "rows": PreviewRow};

type PreviewRow =
	| {
			children: Array<PreviewRow>;
			direction?: "row" | "column";
			display?: Array<string>;
	  }
	| PreviewFieldgroup
	| FixedPreview
	| SettingPreview;

type PreviewProps = {
	relSize?: number;
	direction?: "row" | "column";
	display?: Array<string>;
};
type SettingPreview = {
	setting: string;
} & PreviewProps;

type PreviewFieldgroup =
	| PredefinedFieldgroupPreview
	| PlaceholderFieldGroupPreview;

type FixedPreview = { value: LocalizableString; label?: LocalizableString } & PreviewProps;

type PlaceholderFieldGroupPreview = {
	fieldgroup: string;
} & PreviewProps;

type PredefinedFieldgroupPreview = {
	fieldgroup: string;
	sample: PreviewSample[];
} & PreviewProps;

type PreviewSample = {
	content: LocalizableString;
	label: LocalizableString;
};

type NewPlatformLayout = {
	style: string;
	fieldgroups: {};
	settings: {};
	file_settings: Record<string, WalletFile>;
};
type ServerSideFile = { url: string; name: string };
type ClientSideFile = { file: File | null; identifier?: string };
type WalletFile = ServerSideFile | ClientSideFile;
