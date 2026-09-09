import { defineConfig, globalIgnores } from 'eslint/config'
import globals from 'globals'
import js from '@eslint/js'
import ts from 'typescript-eslint'
import stylistic from '@stylistic/eslint-plugin'
import vue from 'eslint-plugin-vue'
import vuePug from 'eslint-plugin-vue-pug'

const ignores = globalIgnores([
	'**/node_modules',
	'**/dist',
	// Vendored code
	'src/pretix/static/leaflet',
	'src/pretix/static/clipboard',
	'src/pretix/static/cropper',
	'src/pretix/static/lightbox',
	'src/pretix/static/are-you-sure',
	'src/pretix/static/vuejs',
	'src/pretix/static/fontawesome',
	'src/pretix/static/typeahead',
	'src/pretix/static/moment',
	'src/pretix/static/pdfjs',
	'src/pretix/static/sortable',
	'src/pretix/static/iframeresizer',
	'src/pretix/static/bootstrap',
	'src/pretix/static/d3',
	'src/pretix/static/jsi18n',
	'src/pretix/static/fabric',
	'src/pretix/static/datetimepicker',
	'src/pretix/static/charts',
	'src/pretix/static/fileupload',
	'src/pretix/static/seating',
	'src/pretix/static/rest_framework',
	'src/pretix/static/select2',
	'src/pretix/static/schema',
	'src/pretix/static/slider',
	'src/pretix/static/jquery',
	'src/pretix/static/colorpicker',
	'src/pretix/static/rrule',
	// Pre-vue JS code
	'src/pretix/static/pretixbase',
	'src/pretix/static/pretixpresale/js/base64js.js',
	'src/pretix/static/pretixpresale/js/csrfcookieretry.js',
	'src/pretix/static/pretixpresale/js/postmessage.js',
	'src/pretix/static/pretixpresale/js/walletdetection.js',
	'src/pretix/static/pretixcontrol/js/base64js.js',
	'src/pretix/static/pretixcontrol/js/ui/devices.js',
	'src/pretix/static/pretixcontrol/js/ui/webauthn.js',
	'src/pretix/static/pretixcontrol/js/ui/mail.js',
	'src/pretix/static/pretixcontrol/js/ui/question.js',
	'src/pretix/static/pretixcontrol/js/ui/geo.js',
	'src/pretix/static/pretixcontrol/js/ui/hidequota.js',
	'src/pretix/static/pretixcontrol/js/ui/tabs.js',
	'src/pretix/static/pretixcontrol/js/ui/rrule.js',
	'src/pretix/static/pretixcontrol/js/ui/main.js',
	'src/pretix/static/pretixcontrol/js/ui/dragndroplist.js',
	'src/pretix/static/pretixcontrol/js/ui/dashboard.js',
	'src/pretix/static/pretixcontrol/js/ui/editor.js',
	'src/pretix/static/pretixcontrol/js/ui/quota.js',
	'src/pretix/static/pretixcontrol/js/ui/plugins.js',
	'src/pretix/static/pretixcontrol/js/ui/focus.js',
	'src/pretix/static/pretixcontrol/js/ui/variations.js',
	'src/pretix/static/pretixcontrol/js/ui/subevent.js',
	'src/pretix/static/pretixcontrol/js/ui/orderchange.js',
	'src/pretix/static/pretixcontrol/js/ui/quicksetup.js',
	'src/pretix/static/pretixcontrol/js/ui/outgoingmail.js',
	'src/pretix/static/pretixcontrol/js/ui/typeahead.js',
	'src/pretix/static/pretixcontrol/js/auth.js',
	'src/pretix/static/pretixcontrol/js/sb-admin-2.js',
	'src/pretix/static/pretixcontrol/js/menu.js',
	'src/pretix/static/pretixcontrol/js/send_form.js',
	'src/pretix/static/pretixcontrol/js/clipboard.js',
	'src/pretix/static/pretixcontrol/js/js.qrcode.min.js',
	'src/pretix/plugins/statistics/static',
	'src/pretix/plugins/paypal/static',
	'src/pretix/plugins/paypal2/static',
	'src/pretix/plugins/stripe/static',
	'src/pretix/plugins/banktransfer/static',
	// Plugin checkouts
	'local',
])

export default defineConfig([
	ignores,
	...ts.config(
		js.configs.recommended,
		ts.configs.recommended
	),
	stylistic.configs.customize({
		indent: 'tab',
		braceStyle: '1tbs',
		quoteProps: 'as-needed'
	}),
	...vue.configs['flat/recommended'],
	...vuePug.configs['flat/recommended'],
	{
		languageOptions: {
			globals: {
				...globals.browser,
				...globals.node,
				localStorage: false,
				$: 'readonly',
				$$: 'readonly',
				$ref: 'readonly',
				$computed: 'readonly',
			},
			parserOptions: {
				parser: '@typescript-eslint/parser'
			}
		},

		rules: {
			'no-debugger': 'off',
			curly: 0,
			'no-return-assign': 0,
			'no-console': 'off',
			'vue/require-default-prop': 0,
			'vue/require-v-for-key': 0,
			'vue/valid-v-for': 'warn',
			'vue/no-reserved-keys': 0,
			'vue/no-setup-props-destructure': 0,
			'vue/multi-word-component-names': 0,
			'vue/max-attributes-per-line': 0,
			'vue/attribute-hyphenation': ['warn', 'never'],
			'vue/v-on-event-hyphenation': ['warn', 'never'],
			'import/first': 0,
			'@typescript-eslint/ban-ts-comment': 0,
			'@typescript-eslint/no-explicit-any': 0,
			'no-use-before-define': 'off',
			'no-var': 'error',

			'@typescript-eslint/no-use-before-define': ['error', {
				typedefs: false,
				functions: false,
			}],

			'@typescript-eslint/no-unused-vars': ['error', {
				args: 'all',
				argsIgnorePattern: '^_',
				caughtErrors: 'all',
				caughtErrorsIgnorePattern: '^_',
				destructuredArrayIgnorePattern: '^_',
				varsIgnorePattern: '^_',
				ignoreRestSiblings: true
			}],

			'@stylistic/comma-dangle': 0,
			'@stylistic/space-before-function-paren': ['error', 'always'],
			'@stylistic/max-statements-per-line': ['error', { max: 1, ignoredNodes: ['BreakStatement'] }],
			'@stylistic/member-delimiter-style': 0,
			'@stylistic/arrow-parens': 0,
			'@stylistic/generator-star-spacing': 0,
			'@stylistic/yield-star-spacing': ['error', 'after'],
		},
	},
	{
		files: [
			'src/pretix/static/pretixcontrol/js/ui/checkinrules/**/*.vue',
			'src/pretix/plugins/webcheckin/**/*.vue',
		],
		languageOptions: {
			globals: {
				moment: 'readonly',
			},
		},
	},
	{
		files: [
			'src/pretix/static/pretixpresale/widget/**/*.{ts,vue}',
		],
		languageOptions: {
			globals: {
				LANG: 'readonly',
			},
		},
	},
])
