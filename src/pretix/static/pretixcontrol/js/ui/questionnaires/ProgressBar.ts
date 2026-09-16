
type MyAttrs = {
    [key: `on${any}`]: EventListener, style?: {[key:string]: string} | string, innerHTML?: string,
    appendTo?: HTMLElement | ShadowRoot, prependTo?: HTMLElement | ShadowRoot, insertBefore?: HTMLElement, insertAfter?: HTMLElement,
    [key: Exclude<string, 'component' | 'args'>]: any,
};

export function EL<K extends keyof HTMLElementTagNameMap>(tagName: K, attrs:MyAttrs, ...children:(string|HTMLElement)[]): HTMLElementTagNameMap[K];
export function EL(tagName:string, attrs:MyAttrs, ...children:(string|HTMLElement)[]) : HTMLElement;
export function EL(tagName:string, attrs:MyAttrs, ...children:(string|HTMLElement)[]) : HTMLElement {
    if (attrs?.idGetOrCreate) {
        const el = document.getElementById(attrs.idGetOrCreate);
        if (el) {
            return el;
        } else {
            attrs.id = attrs.idGetOrCreate; delete attrs.idGetOrCreate;
        }
    }
	var el = document.createElement(tagName);
	if (attrs) for(var key in attrs)
		if (key === 'style' && typeof attrs[key] === 'object') Object.assign(el.style, attrs[key]);
        else if (key === 'component' && 'args' in attrs) el['Component'] = new attrs.component(el, ...attrs.args);
        else if (key === 'innerHTML') el.innerHTML = attrs[key];
        else if (key === 'appendTo' && (attrs.appendTo instanceof HTMLElement || attrs.appendTo instanceof ShadowRoot)) attrs.appendTo.append(el);
        else if (key === 'prependTo' && (attrs.prependTo instanceof HTMLElement || attrs.prependTo instanceof ShadowRoot)) attrs.prependTo.prepend(el);
        else if (key === 'insertBefore' && attrs.insertBefore instanceof HTMLElement) attrs.insertBefore.before(el);
        else if (key === 'insertAfter' && attrs.insertAfter instanceof HTMLElement) attrs.insertAfter.after(el);
        else if (key.startsWith("on")) el.addEventListener(key.substring(2), attrs[key] as unknown as EventListener, false);
		else if (key.startsWith(":")) el[key.substring(1)] = attrs[key];
        else if (key === 'checked' && 'checked' in el) el.checked = attrs.checked;
        else if (key === 'disabled' && 'disabled' in el) el.disabled = attrs.disabled;
		else if (key === 'selected' && 'selected' in el) el.selected = attrs.selected;
		else if (key === 'multiple' && 'multiple' in el) el.multiple = attrs.multiple;
		else el.setAttribute(key, attrs[key]);

	for(var i=0;i<children.length;i++){
		if (children[i] instanceof HTMLElement) el.appendChild(<HTMLElement>children[i]);
		else if (children[i]) el.appendChild(document.createTextNode(""+children[i]));
	}
	return el;
}

export class ProgressBar {
    private static container : HTMLDivElement = EL('div', { appendTo: document.body, class: 'progressBar' }, EL('div', {class:'progressBarText'}));

    static show(message?: string, max?: number) {
        const texts = ProgressBar.container.lastElementChild;
        const bar = EL('div', {class:'progressBar_progress'+(max ? '' : ' indeterminate')});
        let text : HTMLElement;
        if (message) {
            text = EL('span', {}, message);
            texts.append(text);
        }
        texts.before(bar);
        return {
            disposed: false,
            [Symbol.dispose]() {
                if (this.disposed) return;
                bar.remove();
                if (text) text.remove();
                this.disposed = true;
            },
            set message(val: string) {
                text.innerText = val;
            },
            set progress(val: number) {
                if (max) bar.style.width = `${val / max * 100}%`;
            }
        };
    }
}
