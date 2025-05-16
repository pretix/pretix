/*global $,gettext,ngettext */
function EL(tagName, attrs) {
    var el = document.createElement(tagName);
    if (attrs) for(var key in attrs)
        if (key === 'style' && typeof attrs[key] === 'object') Object.assign(el.style, attrs[key]);
        else if (key === 'innerHTML') el.innerHTML = attrs[key];
        else if (key === 'appendTo' && (attrs.appendTo instanceof HTMLElement || attrs.appendTo instanceof ShadowRoot)) attrs.appendTo.append(el);
        else if (key === 'prependTo' && (attrs.prependTo instanceof HTMLElement || attrs.prependTo instanceof ShadowRoot)) attrs.prependTo.prepend(el);
        else if (key === 'insertBefore' && attrs.insertBefore instanceof HTMLElement) attrs.insertBefore.before(el);
        else if (key === 'insertAfter' && attrs.insertAfter instanceof HTMLElement) attrs.insertAfter.after(el);
        else if (key.startsWith("on")) el.addEventListener(key.substring(2), attrs[key], false);
		else if (key.startsWith(":")) el[key.substring(1)] = attrs[key];
		else if (key === 'checked' && 'checked' in el) el.checked = attrs.checked;
		else if (key === 'selected' && 'selected' in el) el.selected = attrs.selected;
		else if (key === 'multiple' && 'multiple' in el) el.multiple = attrs.multiple;
        else el.setAttribute(key, attrs[key]);

    if (arguments[2] instanceof Array)
        var args = arguments[2], i = 0;
    else
        var args = arguments, i = 2;
    for(;i<args.length;i++){
        if (args[i] instanceof HTMLElement) el.appendChild(args[i]);
        else if (args[i]) el.appendChild(document.createTextNode(""+args[i]));
    }
    return el;
}

function ModalDialog(options) {
    this.id = 'modal-dlg-' + (++ModalDialog._next_dialog_id);
    this.options = options;
    this.dialogEl = EL('dialog', {class: 'modal-card', id: this.id,
            'aria-live': 'polite', 'aria-labelledby': this.id + '-title', 'aria-describedby': this.id + '-desc',
            appendTo: document.body, onclose: this._onClose.bind(this)},
        (options.icon)
            ? EL('div', {class: 'modal-card-icon'},
                EL('i', {'aria-hidden': 'true', class: 'fa fa-' + options.icon + ' ' + (options.rotatingIcon ? 'big-rotating-icon' : 'big-icon')}))
            : undefined,
        EL('div', {class: 'modal-card-content'},
            this.titleEl = EL('h3', {id: this.id + '-title'}, options.title || ''),
            this.descEl = EL('p', {id: this.id + '-desc'}, options.description || ''),
            this.contentEl = EL('div', {}, options.content || '')));
}

ModalDialog._next_dialog_id = 1;
ModalDialog.updateBodyClass = function() {
    if ($("dialog[open], .modal-wrapper:not([hidden])").length)
        $(document.body).addClass('has-modal-dialog');
    else
        $(document.body).removeClass('has-modal-dialog');
}

ModalDialog.prototype.show = function() {
    this.dialogEl.showModal();
    ModalDialog.updateBodyClass();
}
ModalDialog.prototype.hide = function() {
    this.dialogEl.close();
}
ModalDialog.prototype.isOpen = function() {
    return this.dialogEl.open;
}
ModalDialog.prototype._onClose = function() {
    if (this.options.removeOnClose) this.dialogEl.remove();
    ModalDialog.updateBodyClass();
}
ModalDialog.prototype.setTitle = function(text) {
    this.titleEl.innerText = text;
}
ModalDialog.prototype.setDescription = function(text) {
    this.descEl.innerText = text;
    this.descEl.style.display = text ? '' : 'none';
}
ModalDialog.prototype.setContent = function(text) {
    this.contentEl.innerText = text;
}
