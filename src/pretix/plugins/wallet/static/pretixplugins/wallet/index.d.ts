type BaseFieldGroupDefinition = {
	type: string;
	identifier: string;
	name: string;
	required: boolean;
	description: string;
};

type FieldGroupDefinition =
	| PlaceholderFieldGroupDefinition
	| PredefinedFieldGroupDefinition;

type FieldGroupDisplay = "plain" | "with_label" | "code";

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

type I18nString = null | string | Record<string, string>;

type FieldContentType = "text" | "image";

type PlaceholderFieldEntry = {
	type: "placeholder";
	label?: I18nString;
	content?: string;
};

type CustomFieldEntry = {
	type: "custom";
	label?: I18nString;
	content?: I18nString;
};

type FieldEntry = PlaceholderFieldEntry | CustomFieldEntry;

type Style = {
	identifier: string;
	name: string;
	fieldgroups: FieldGroupDefinition[];
};

type Variable = {
	label: string;
	sample: string;
	required_context: string[];
};

type Platform = {
	identifier: string;
	name: string;
	styles: Styles;
};

type Styles = Record<string, Style>;
type Variables = Record<string, Variable>;
type VariableConfig = Record<string, Variables>;
type Platforms = Platform[];

type PlaceholderFieldGroupConfig = {
	entries: Array<FieldEntry>;
	overflow: string | null;
	active: boolean;
};

type PredefinedFieldGroupConfig = {
	active: boolean;
};

type FieldGroupConfig =
	| PlaceholderFieldGroupConfig
	| PredefinedFieldGroupConfig;

type LayoutData = {
	fieldgroups: Record<string, FieldGroupConfig>;
};

type PlatformLayout = {
	platform: string;
	style: string | null;
	layout: LayoutData;
};

type WalletLayout = {
	name?: string;
	platform_layouts: PlatformLayout[];
};
type WalletStore = {
	platforms: Platforms;
	variables: VariableConfig;
	locales: Record<string, string>;
	csrfToken: String;
	walletLayout: WalletLayout | null;
};

type PreviewLayout = Array<PreviewRow>;
type PreviewRow =
	| { children: Array<PreviewRow>; direction?: "row" | "column"; display?: Array<string>;}
	| PreviewFieldgroup
	| FixedPreview;

type PreviewProps = {
	relSize?: number;
	direction?: "row" | "column";
	display?: Array<string>;
}

type PreviewFieldgroup = PredefinedFieldgroupPreview | PlaceholderFieldGroupPreview;
type FixedPreview = {
	value: I18nString;
} & PreviewProps

type PlaceholderFieldGroupPreview = {
	fieldgroup: string;
} & PreviewProps;

type PredefinedFieldgroupPreview = {
	fieldgroup: string;
	sample: PreviewSample[];
} & PreviewProps;

type PreviewSample = {
	content: I18nString;
	label: I18nString;
}