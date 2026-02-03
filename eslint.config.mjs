import { defineConfig, globalIgnores } from 'eslint/config'
import globals from 'globals'
import js from '@eslint/js'
import ts from 'typescript-eslint'
import stylistic from '@stylistic/eslint-plugin'
import vue from 'eslint-plugin-vue'
import vuePug from 'eslint-plugin-vue-pug'

const ignores = globalIgnores([
	'**/node_modules',
	'**/dist'
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
	}
])
