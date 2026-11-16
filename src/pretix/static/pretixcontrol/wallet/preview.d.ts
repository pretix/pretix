export type PreviewProps = {
	data: any;
	fieldgroups: Record<string, FieldGroupConfig>;
	fieldgroupContents: Record<
		string,
		{ label?: LocalizableString; content: LocalizableString }
	>;
	settings: Record<string, SettingValue>;
}
