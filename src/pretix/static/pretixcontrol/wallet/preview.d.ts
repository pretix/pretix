import { VueElement } from 'vue'

export type PreviewProps = {
	data: any;
	fieldgroups: Record<string, FieldGroupConfig>;
	fieldgroupContents: Record<
		string,
		{ label?: LocalizableString; content: LocalizableString }
	>;
	settings: Record<string, SettingValue>;
}

declare global {
	interface Window {
		pretix_wallet_preview_renderers: Record<string, VueElement>;
	}
}
