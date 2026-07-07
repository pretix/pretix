import { createApp } from "vue";
import App from "./components/app.vue";
import { createWalletStore, StoreKey } from "./walletStore";
const mountEl = document.querySelector<HTMLElement>("#editor")!;
const store = createWalletStore({
	platforms: JSON.parse(
		document.querySelector("#platforms")?.textContent ?? "{}",
	),
	variables: JSON.parse(
		document.querySelector("#variables")?.textContent ?? "{}",
	),
	locales: JSON.parse(document.querySelector("#locales")?.textContent ?? "{}"),
	csrfToken: document.querySelector<HTMLInputElement>(
		"input[name=csrfmiddlewaretoken]",
	)?.value!!,
	layoutId: mountEl.dataset.layoutId!
});
store.load();
const app = createApp(App);
app.provide(StoreKey, store);
app.mount(mountEl);

app.config.errorHandler = (error, _vm, info) => {
	// vue fatals on errors by default, which is a weird choice
	// https://github.com/vuejs/core/issues/3525
	// https://github.com/vuejs/router/discussions/2435
	console.error("[VUE]", info, error);
};
