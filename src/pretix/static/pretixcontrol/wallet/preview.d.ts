export type PreviewProps = {
	data: any;
	fieldgroups: Record<string, FieldGroupConfig>;
	fieldgroup_contents: Record<
		string,
		{ label?: LocalizableString; content: LocalizableString }
	>;
	settings: Record<string, SettingValue>;
}
