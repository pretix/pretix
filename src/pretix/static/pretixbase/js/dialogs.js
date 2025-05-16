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
var dialog_id = 1;
function ModalDialog(options) {
    this.id = 'modal-dlg-' + (++dialog_id);
    this.dialogEl = EL('dialog', {class: 'modal-card', 'aria-live': 'polite',
            'aria-labelledby': this.id + '-title', 'aria-describedby': this.id + '-desc',
            appendTo: document.body, onclose: this._onClose.bind(this)},
        this.iconEl =
            (options.icon)
            ? EL('div', {class: 'modal-card-icon'},
                EL('i', {'aria-hidden': 'true', class: 'fa fa-' + options.icon + ' ' + (options.rotatingIcon ? 'big-rotating-icon' : 'big-icon')}))
            : undefined,
        EL('div', {class: 'modal-card-content'},
            this.titleEl = EL('h3', {id: this.id + '-title'}, options.title || ''),
            this.contentEl = EL('div', {id: this.id + '-desc'}, options.content || '')));
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
    ModalDialog.updateBodyClass();
}
ModalDialog.prototype.setTitle = function(text) {
    this.titleEl.innerText = text;
}
ModalDialog.prototype.setContent = function(text) {
    this.contentEl.innerText = text;
}
ModalDialog.updateBodyClass = function() {
    if ($("dialog[open], .modal-wrapper:not([hidden])").length)
        $(document.body).addClass('has-modal-dialog');
    else
        $(document.body).removeClass('has-modal-dialog');
}





    /*
function ModalDialog(options) {
    this.backdropEl = document.createElement('div');
    this.backdropEl.className = 'modal-wrapper';
    this.backdropEl.setAttribute('hidden', 'hidden');
    this.dialogEl = document.createElement('div');
    this.dialogEl.className = 'modal-card';
    this.backdropEl.appendChild(this.dialogEl);
    if (options.icon) {
        this.iconEl = document.createElement('div');
        this.iconEl.className = 'modal-card-icon';
        this.dialogEl.appendChild(this.iconEl);
        var icon = document.createElement('i');
        icon.setAttribute('aria-hidden', 'true');
        icon.className = 'fa fa-' + options.icon + ' ' + (options.rotatingIcon ? 'big-rotating-icon' : 'big-icon');
    }
    this.dialogContentEl = document.createElement('div');
    this.dialogContentEl.className = 'modal-card-content';
    this.titleEl = document.createElement('h3');
    this.dialogContentEl.appendChild(this.titleEl);
    this.descriptionEl = document.createElement('div');
    this.dialogContentEl.appendChild(this.descriptionEl);
    this.backdropEl.appendChild(this.contentEl);
    document.body.appendChild(this.backdropEl);
    this.setTitle(options.title || '');
    this.setDescription(options.description || '');
}
    */