import { reactive, computed, watch } from 'vue'
import type { WatchCallback, WatchOptions, UnwrapNestedRefs } from 'vue'

interface StoreMethods {
	$reset: () => void
	$watch: <T>(source: () => T, callback: WatchCallback<T>, options?: WatchOptions) => void
}

type GetterReturnTypes<G> = {
	readonly [K in keyof G]: G[K] extends () => infer R ? R : never
}

type Store<S, G, A> = UnwrapNestedRefs<S> & GetterReturnTypes<G> & A & StoreMethods
type GettersTree<S> = Record<string, (this: S, state: S) => any> | Record<string, () => any>
type ActionsTree = Record<string, (...args: any[]) => any>

export function createStore<
	S extends object,
	G extends GettersTree<S>,
	A extends ActionsTree
> (
	// name: string,
	config: {
		state: () => S
		getters?: G & ThisType<UnwrapNestedRefs<S> & GetterReturnTypes<G> & A & StoreMethods>
		actions?: A & ThisType<UnwrapNestedRefs<S> & GetterReturnTypes<G> & A & StoreMethods>
	}
): Store<S, G, A> {
	type StoreType = Store<S, G, A>
	const store = reactive(config.state()) as StoreType

	// Add getters as computed properties
	if (config.getters) {
		for (const key of Object.keys(config.getters) as (keyof G)[]) {
			const getter = config.getters[key]
			const computedRef = computed(() => (getter as () => unknown).call(store))
			Object.defineProperty(store, key, {
				get: () => computedRef.value,
				enumerable: true
			})
		}
	}

	// Add actions bound to the store
	if (config.actions) {
		for (const key of Object.keys(config.actions) as (keyof A)[]) {
			const action = config.actions[key]
			;(store as Record<string, unknown>)[key as string] = (action as (...args: unknown[]) => unknown).bind(store)
		}
	}

	store.$reset = function () {
		const cleanState = config.state()
		const cleanKeys = new Set([
			'$reset',
			'$watch',
			...Object.keys(cleanState),
			...Object.keys(config.getters ?? {}),
			...Object.keys(config.actions ?? {})
		])

		// Delete any keys that aren't in clean state and aren't known non-state keys
		for (const key of Object.keys(store)) {
			if (!cleanKeys.has(key)) {
				delete (store as Record<string, unknown>)[key]
			}
		}

		// Set all state values from clean state
		for (const key of Object.keys(cleanState) as (keyof S)[]) {
			;(store as S)[key] = cleanState[key]
		}
	}

	store.$watch = function <T>(source: () => T, callback: WatchCallback<T>, options?: WatchOptions) {
		watch(source.bind(store), callback.bind(store), options)
	}

	return store
}
