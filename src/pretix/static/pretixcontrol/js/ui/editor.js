/*globals $, gettext, fabric, PDFJS*/
fabric.Poweredby = fabric.util.createClass(fabric.Image, {
    type: 'poweredby',

    initialize: function (options) {
        options || (options = {});

        this.callSuper('initialize', $("#poweredby-" + options.content).get(0), options);
        this.set('label', options.label || '');
    },

    toObject: function () {
        return fabric.util.object.extend(this.callSuper('toObject'), {});
    },

    _render: function (ctx) {
        this.callSuper('_render', ctx);
    },
});
fabric.Poweredby.fromObject = function (object, callback, forceAsync) {
    return fabric.Object._fromObject('Poweredby', object, callback, forceAsync);
};
fabric.Barcodearea = fabric.util.createClass(fabric.Rect, {
    type: 'barcodearea',

    initialize: function (text, options) {
        options || (options = {});

        this.callSuper('initialize', text, options);
        this.set('label', options.label || '');
    },

    toObject: function () {
        return fabric.util.object.extend(this.callSuper('toObject'), {});
    },

    _render: function (ctx) {
        this.callSuper('_render', ctx);

        ctx.font = '16px Helvetica';
        ctx.fillStyle = '#fff';
        if (this.content === "pseudonymization_id") {
            ctx.fillText(gettext('Lead Scan QR'), -this.width / 2, -this.height / 2 + 20);
        } else {
            ctx.fillText(gettext('Check-in QR'), -this.width / 2, -this.height / 2 + 20);
        }
    },
});
fabric.Barcodearea.fromObject = function (object, callback, forceAsync) {
    return fabric.Object._fromObject('Barcodearea', object, callback, forceAsync);
};
fabric.Textarea = fabric.util.createClass(fabric.Textbox, {
    type: 'textarea',

    initialize: function (text, options) {
        options || (options = {});

        this.callSuper('initialize', text, options);
        this.set('content', options.content || '');
    },

    toObject: function(propertiesToInclude) {
        return this.callSuper('toObject', ['content'].concat(propertiesToInclude));
    }
});
fabric.Textarea.fromObject = function (object, callback, forceAsync) {
    return fabric.Object._fromObject('Textarea', object, callback, forceAsync, 'text');
};


var editor = {
    $pdfcv: null,
    $fcv: null,
    $cva: null,
    $fabric: null,
    objects: [],
    history: [],
    clipboard: [],
    pdf_page: null,
    pdf_scale: 1,
    pdf_viewport: null,
    _history_pos: 0,
    _history_modification_in_progress: false,
    dirty: false,
    pdf_url: null,
    uploaded_file_id: null,
    _window_loaded: false,
    _fabric_loaded: false,

    _px2mm: function (v) {
        return v / editor.pdf_scale / 72 * editor.pdf_page.userUnit * 25.4;
    },

    _mm2px: function (v) {
        return v * editor.pdf_scale * 72 / editor.pdf_page.userUnit / 25.4;
    },

    _px2pt: function (v) {
        return v / editor.pdf_scale * editor.pdf_page.userUnit;
    },

    _pt2px: function (v) {
        return v * editor.pdf_scale / editor.pdf_page.userUnit;
    },

    dump: function (objs) {
        var d = [];
        objs = objs || editor.fabric.getObjects();

        for (var i in objs) {
            var o = objs[i];
            var top = o.top;
            var left = o.left;
            if (o.group) {
                top += o.group.top + o.group.height / 2;
                left += o.group.left + o.group.width / 2;
            }
            if (o.type === "textarea") {
                var col = (new fabric.Color(o.getFill()))._source;
                var bottom = editor.pdf_viewport.height - o.height - top;
                if (o.downward) {
                    bottom = editor.pdf_viewport.height - top;
                }
                d.push({
                    type: "textarea",
                    locale: $("#pdf-info-locale").val(),
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(bottom).toFixed(2),
                    fontsize: editor._px2pt(o.getFontSize()).toFixed(1),
                    color: col,
                    //lineheight: o.lineHeight,
                    fontfamily: o.fontFamily,
                    bold: o.fontWeight === 'bold',
                    italic: o.fontStyle === 'italic',
                    width: editor._px2mm(o.width).toFixed(2),
                    downward: o.downward || false,
                    content: o.content,
                    text: o.text,
                    rotation: o.angle,
                    align: o.textAlign,
                });
            } else  if (o.type === "barcodearea") {
                d.push({
                    type: "barcodearea",
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(editor.pdf_viewport.height - o.height * o.scaleY - top).toFixed(2),
                    size: editor._px2mm(o.height * o.scaleY).toFixed(2),
                    content: o.content,
                });
            } else  if (o.type === "poweredby") {
                d.push({
                    type: "poweredby",
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(editor.pdf_viewport.height - o.height * o.scaleY - top).toFixed(2),
                    size: editor._px2mm(o.height * o.scaleY).toFixed(2),
                    content: o.content,
                });
            }
        }
        return d;
    },

    _add_from_data: function (d) {
        if (d.type === "barcodearea") {
            o = editor._add_qrcode();
            o.content = d.content;
            o.scaleToHeight(editor._mm2px(d.size));
        } else if (d.type === "poweredby") {
            o = editor._add_poweredby(d.content);
            o.content = d.content;
            o.scaleToHeight(editor._mm2px(d.size));
        } else if (d.type === "textarea" || o.type === "text") {
            o = editor._add_text();
            o.setColor('rgb(' + d.color[0] + ',' + d.color[1] + ',' + d.color[2] + ')');
            o.setFontSize(editor._pt2px(d.fontsize));
            //o.setLineHeight(d.lineheight);
            o.setFontFamily(d.fontfamily);
            o.setFontWeight(d.bold ? 'bold' : 'normal');
            o.setFontStyle(d.italic ? 'italic' : 'normal');
            o.setWidth(editor._mm2px(d.width));
            o.downward = d.downward || false;
            o.content = d.content;
            o.setTextAlign(d.align);
            o.rotate(d.rotation);
            if (d.content === "other") {
                o.setText(d.text);
            } else {
                o.setText(editor._get_text_sample(d.content));
            }
            if (d.locale) {
                // The data format allows to set the locale per text field but we currently only expose a global field
                $("#pdf-info-locale").val(d.locale);
            }
        }

        var new_top = editor.pdf_viewport.height - editor._mm2px(d.bottom) - (o.height * o.scaleY);
        if (o.downward) {
            new_top = editor.pdf_viewport.height - editor._mm2px(d.bottom);
        }
        o.set('left', editor._mm2px(d.left));
        o.set('top', new_top);
        o.setCoords();
        return o;
    },

    load: function(data) {
        editor.fabric.clear();
        for (var i in data) {
            var d = data[i], o;
            editor._add_from_data(d);
        }
        editor.fabric.renderAll();
        editor._update_toolbox_values();
    },

    _get_text_sample: function (key) {
        if (key.startsWith('meta:')) {
            return key.substr(5);
        }
        return $('#toolbox-content option[value='+key+']').attr('data-sample') || '';
    },

    _load_pdf: function (dump) {
        // TODO: Loading indicators
        var url = editor.pdf_url;
        // TODO: Handle cross-origin issues if static files are on a different origin
        PDFJS.workerSrc = editor.$pdfcv.attr("data-worker-url");

        // Asynchronous download of PDF
        var loadingTask = PDFJS.getDocument(url);
        loadingTask.promise.then(function (pdf) {
            console.log('PDF loaded');

            // Fetch the first page
            var pageNumber = 1;
            pdf.getPage(pageNumber).then(function (page) {
                console.log('Page loaded');
                var canvas = document.getElementById('pdf-canvas');

                var scale = editor.$cva.width() / page.getViewport(1.0).width;
                var viewport = page.getViewport(scale);

                // Prepare canvas using PDF page dimensions
                var context = canvas.getContext('2d');
                context.clearRect(0, 0, canvas.width, canvas.height);
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                editor.pdf_page = page;
                editor.pdf_scale = scale;
                editor.pdf_viewport = viewport;

                // Render PDF page into canvas context
                var renderContext = {
                    canvasContext: context,
                    viewport: viewport
                };
                var renderTask = page.render(renderContext);
                renderTask.then(function () {
                    console.log('Page rendered');
                    editor._init_fabric(dump);
                });
            });
        }, function (reason) {
            var msg = gettext('The PDF background file could not be loaded for the following reason:');
            editor._error(msg + ' ' + reason);
        });
    },

    _init_fabric: function (dump) {
        editor.$fcv.get(0).width = editor.$pdfcv.get(0).width;
        editor.$fcv.get(0).height = editor.$pdfcv.get(0).height;
        editor.fabric = new fabric.Canvas('fabric-canvas');

        editor.fabric.on('object:modified', editor._create_savepoint);
        editor.fabric.on('object:added', editor._create_savepoint);
        editor.fabric.on('selection:cleared', editor._update_toolbox);
        editor.fabric.on('selection:created', editor._update_toolbox);
        editor.fabric.on('object:selected', editor._update_toolbox);
        editor.fabric.on('object:moving', editor._update_toolbox_values);
        editor.fabric.on('object:modified', editor._update_toolbox_values);
        editor.fabric.on('object:rotating', editor._update_toolbox_values);
        editor.fabric.on('object:scaling', editor._update_toolbox_values);
        editor._update_toolbox();

        $("#toolbox-content-other").hide();
        $(".add-buttons button").prop('disabled', false);

        if (dump) {
            editor.load(dump);
        } else {
            var data = $.trim($("#editor-data").text());
            if (data) {
                editor.load(JSON.parse(data));
            }
        }
        editor.history = [];
        editor._create_savepoint();
        editor.dirty = !!dump;

        if ($("#loading-upload").is(":visible")) {
            $("#loading-container, #loading-upload").hide();
        }

        editor._fabric_loaded = true;
        console.log("Fabric loaded");
        if (editor._window_loaded) {
            editor._ready();
        }
    },

    _window_load_event: function () {
        editor._window_loaded = true;
        console.log("Window loaded");
        if (editor._fabric_loaded) {
            editor._ready();
        }
    },

    _ready: function () {
        $("#editor-loading").hide();
        $("#editor-start").removeClass("sr-only");
        $("#editor-start").click(function () {
            $("#loading-container").hide();
            $("#loading-initial").remove();
        });
    },

    _update_toolbox_values: function () {
        var o = editor.fabric.getActiveObject();
        if (!o) {
            o = editor.fabric.getActiveGroup();
            if (!o) {
                return;
            }
        }
        var bottom = editor.pdf_viewport.height - o.height * o.scaleY - o.top;
        if (o.downward) {
            bottom = editor.pdf_viewport.height - o.top;
        }
        $("#toolbox-position-x").val(editor._px2mm(o.left).toFixed(2));
        $("#toolbox-position-y").val(editor._px2mm(bottom).toFixed(2));

        if (o.type === "barcodearea") {
            $("#toolbox-squaresize").val(editor._px2mm(o.height * o.scaleY).toFixed(2));
        } else if (o.type === "poweredby") {
            $("#toolbox-squaresize").val(editor._px2mm(o.height * o.scaleY).toFixed(2));
            $("#toolbox-poweredby-style").val(o.content);
        } else if (o.type === "text" || o.type === "textarea") {
            var col = (new fabric.Color(o.getFill()))._source;
            $("#toolbox-col").val("#" + ((1 << 24) + (col[0] << 16) + (col[1] << 8) + col[2]).toString(16).slice(1));
            $("#toolbox-fontsize").val(editor._px2pt(o.fontSize).toFixed(1));
            //$("#toolbox-lineheight").val(o.lineHeight);
            $("#toolbox-fontfamily").val(o.fontFamily);
            $("#toolbox").find("button[data-action=bold]").toggleClass('active', o.fontWeight === 'bold');
            $("#toolbox").find("button[data-action=italic]").toggleClass('active', o.fontStyle === 'italic');
            $("#toolbox").find("button[data-action=downward]").toggleClass('active', o.downward || false);
            $("#toolbox").find("button[data-action=left]").toggleClass('active', o.textAlign === 'left');
            $("#toolbox").find("button[data-action=center]").toggleClass('active', o.textAlign === 'center');
            $("#toolbox").find("button[data-action=right]").toggleClass('active', o.textAlign === 'right');
            $("#toolbox-textwidth").val(editor._px2mm(o.width).toFixed(2));
            $("#toolbox-textrotation").val((o.angle || 0.0).toFixed(1));
            if (o.type === "textarea") {
                $("#toolbox-content").val(o.content);
                $("#toolbox-content-other").toggle($("#toolbox-content").val() === "other");
                if (o.content === "other") {
                    $("#toolbox-content-other").val(o.text);
                } else {
                    $("#toolbox-content-other").val("");
                }
            }
        }
    },

    _update_values_from_toolbox: function () {
        var o = editor.fabric.getActiveObject();
        if (!o) {
            o = editor.fabric.getActiveGroup();
            if (!o) {
                return;
            }
        }

        var new_top = editor.pdf_viewport.height - editor._mm2px($("#toolbox-position-y").val()) - o.height * o.scaleY;
        if (o.type === "textarea" || o.type === "text") {
            if ($("#toolbox").find("button[data-action=downward]").is('.active')) {
                new_top = editor.pdf_viewport.height - editor._mm2px($("#toolbox-position-y").val());
            }
        }
        o.set('left', editor._mm2px($("#toolbox-position-x").val()));
        o.set('top', new_top);

        if (o.type === "barcodearea") {
            var new_h = editor._mm2px($("#toolbox-squaresize").val());
            new_top += o.height * o.scaleY - new_h;
            o.setHeight(new_h);
            o.setWidth(new_h);
            o.setScaleX(1);
            o.setScaleY(1);
            o.set('top', new_top)
        } else if (o.type === "poweredby") {
            var new_h = Math.max(1, editor._mm2px($("#toolbox-squaresize").val()));
            new_top += o.height * o.scaleY - new_h;
            o.setWidth(new_h / o.height * o.width);
            o.setHeight(new_h);
            o.setScaleX(1);
            o.setScaleY(1);
            o.set('top', new_top)
            if ($("#toolbox-poweredby-style").val() !== o.content) {
                var data = editor.dump([o]);
                data[0].content = $("#toolbox-poweredby-style").val();
                var newo = editor._add_from_data(data[0]);
                o.remove();
                editor.fabric.discardActiveGroup();
                editor.fabric.discardActiveObject();
                editor.fabric.setActiveObject(newo);
            }
        } else if (o.type === "textarea" || o.type === "text") {
            o.setColor($("#toolbox-col").val());
            o.setFontSize(editor._pt2px($("#toolbox-fontsize").val()));
            //o.setLineHeight($("#toolbox-lineheight").val());
            o.setFontFamily($("#toolbox-fontfamily").val());
            o.setFontWeight($("#toolbox").find("button[data-action=bold]").is('.active') ? 'bold' : 'normal');
            o.setFontStyle($("#toolbox").find("button[data-action=italic]").is('.active') ? 'italic' : 'normal');
            var align = $("#toolbox-align").find(".active").attr("data-action");
            if (align) {
                o.setTextAlign(align);
            }
            o.setWidth(editor._mm2px($("#toolbox-textwidth").val()));
            o.downward = $("#toolbox").find("button[data-action=downward]").is('.active');
            o.rotate(parseFloat($("#toolbox-textrotation").val()));
            $("#toolbox-content-other").toggle($("#toolbox-content").val() === "other");
            o.content = $("#toolbox-content").val();
            if ($("#toolbox-content").val() === "other") {
                o.setText($("#toolbox-content-other").val());
            } else {
                o.setText(editor._get_text_sample($("#toolbox-content").val()));
            }
        }

        o.setCoords();
        editor.fabric.renderAll();
    },

    _update_toolbox: function () {
        if (editor.fabric.getActiveGroup()) {
            $("#toolbox").attr("data-type", "group");
            $("#toolbox-heading").text(gettext("Group of objects"));
            var g = editor.fabric.getActiveGroup();
        } else if (editor.fabric.getActiveObject()) {
            var o = editor.fabric.getActiveObject();
            $("#toolbox").attr("data-type", o.type);
            if (o.type === "textarea" || o.type === "text") {
                $("#toolbox-heading").text(gettext("Text object"));
            } else if (o.type === "barcodearea") {
                $("#toolbox-heading").text(gettext("Barcode area"));
            } else if (o.type === "poweredby") {
                $("#toolbox-heading").text(gettext("Powered by pretix"));
            } else {
                $("#toolbox-heading").text(gettext("Object"));
            }
        } else {
            $("#toolbox").removeAttr("data-type");
            $("#toolbox-heading").text(gettext("Ticket design"));
            $("#pdf-info-width").val(editor._px2mm(editor.pdf_viewport.width).toFixed(2));
            $("#pdf-info-height").val(editor._px2mm(editor.pdf_viewport.height).toFixed(2));
        }
        editor._update_toolbox_values();
    },

    _error: function (msg) {
        editor.$cva.before("<div class='alert alert-danger'>" + msg + "</div>");
    },

    _add_text: function () {
        var text = new fabric.Textarea(editor._get_text_sample('event_name'), {
            left: 100,
            top: 100,
            width: editor._mm2px(50),
            lockRotation: false,
            fontFamily: 'Open Sans',
            lineHeight: 1,
            content: 'item',
            editable: false,
            fontSize: editor._pt2px(13)
        });
        text.downward = true;
        text.setControlsVisibility({
            'tr': false,
            'tl': false,
            'mt': false,
            'br': false,
            'bl': false,
            'mb': false,
            'mr': true,
            'ml': true,
            'mtr': true
        });
        editor.fabric.add(text);
        editor._create_savepoint();
        return text;
    },

    _add_poweredby: function (content) {
        var rect = new fabric.Poweredby({
            left: 100,
            top: 100,
            width: 205,
            height: 126,
            lockRotation: true,
            lockUniScaling: true,
            content: content
        });
        rect.setControlsVisibility({'mtr': false});
        editor.fabric.add(rect);
        editor._create_savepoint();
        return rect;
    },

    _add_qrcode: function () {
        var rect = new fabric.Barcodearea({
            left: 100,
            top: 100,
            width: 100,
            height: 100,
            lockRotation: true,
            lockUniScaling: true,
            fill: '#666',
            content: $(this).attr("data-content"),
        });
        rect.setControlsVisibility({'mtr': false});
        editor.fabric.add(rect);
        editor._create_savepoint();
        return rect;
    },

    _cut: function () {
        editor._history_modification_in_progress = true;
        var thing = editor.fabric.getActiveObject() ? editor.fabric.getActiveObject() : editor.fabric.getActiveGroup();
        if (thing.type === "group") {
            editor.clipboard = editor.dump(thing._objects);
            thing.forEachObject(function (o) {
                o.remove();
            });
            thing.remove();
        } else {
            editor.clipboard = editor.dump([thing]);
            thing.remove();
        }
        editor.fabric.discardActiveGroup();
        editor.fabric.discardActiveObject();
        editor._history_modification_in_progress = false;
        editor._create_savepoint();
    },

    _copy: function () {
        editor._history_modification_in_progress = true;
        var thing = editor.fabric.getActiveObject() ? editor.fabric.getActiveObject() : editor.fabric.getActiveGroup();
        if (thing.type === "group") {
            editor.clipboard = editor.dump(thing._objects);
        } else {
            editor.clipboard = editor.dump([thing]);
        }
        editor._history_modification_in_progress = false;
        editor._create_savepoint();
    },

    _paste: function () {
        if (editor.clipboard.length < 1) {
            return;
        }
        editor._history_modification_in_progress = true;
        var objs = [];
        for (var i in editor.clipboard) {
            objs.push(editor._add_from_data(editor.clipboard[i]));
        }
        editor.fabric.discardActiveObject();
        editor.fabric.discardActiveGroup();
        if (editor.clipboard.length > 1) {
            var group = new fabric.Group(objs, {
                originX: 'left',
                originY: 'top',
                left: 100,
                top: 100,
            });
            group.setCoords();
            editor.fabric.setActiveGroup(group);
        } else {
            editor.fabric.setActiveObject(objs[0]);
        }
        editor._history_modification_in_progress = false;
        editor._create_savepoint();
    },

    _delete: function () {
        var thing = editor.fabric.getActiveObject() ? editor.fabric.getActiveObject() : editor.fabric.getActiveGroup();
        if (thing.type === "group") {
            thing.forEachObject(function (o) {
                o.remove();
            });
            thing.remove();
            editor.fabric.discardActiveGroup();
        } else {
            thing.remove();
            editor.fabric.discardActiveObject();
        }
        editor._create_savepoint();
    },

    _on_keydown: function (e) {
        var step = e.shiftKey ? editor._mm2px(10) : editor._mm2px(1);
        var thing = editor.fabric.getActiveObject() ? editor.fabric.getActiveObject() : editor.fabric.getActiveGroup();
        if ($("#source-container").is(':visible')) {
            return true;
        }
        switch (e.keyCode) {
            case 38:  /* Up arrow */
                thing.set('top', thing.get('top') - step);
                thing.setCoords();
                editor._create_savepoint();
                break;
            case 40:  /* Down arrow */
                thing.set('top', thing.get('top') + step);
                thing.setCoords();
                editor._create_savepoint();
                break;
            case 37:  /* Left arrow  */
                thing.set('left', thing.get('left') - step);
                thing.setCoords();
                editor._create_savepoint();
                break;
            case 39:  /* Right arrow  */
                thing.set('left', thing.get('left') + step);
                thing.setCoords();
                editor._create_savepoint();
                break;
            case 46:  /* Delete */
                editor._delete();
                break;
            case 89:  /* Y */
                if (e.ctrlKey) {
                    editor._redo();
                }
                break;
            case 90:  /* Z */
                if (e.ctrlKey) {
                    editor._undo();
                }
                break;
            case 88:  /* X */
                if (e.ctrlKey) {
                    editor._cut();
                }
                break;
            case 86:  /* V */
                if (e.ctrlKey) {
                    editor._paste();
                }
                break;
            case 67:  /* C */
                if (e.ctrlKey) {
                    editor._copy();
                }
                break;
            default:
                return;
        }
        e.preventDefault();
        editor.fabric.renderAll();
        editor._update_toolbox_values();
    },

    _create_savepoint: function () {
        if (editor._history_modification_in_progress) {
            return;
        }
        var state = editor.dump();
        if (editor._history_pos > 0) {
            editor.history.splice(-1 * editor._history_pos, editor._history_pos);
            editor._history_pos = 0;
        }
        editor.history.push(state);
        editor.dirty = true;
    },

    _undo: function undo() {
        if (editor._history_pos < editor.history.length - 1) {
            editor._history_modification_in_progress = true;
            editor._history_pos += 1;
            editor.fabric.clear().renderAll();
            editor.load(editor.history[editor.history.length - 1 - editor._history_pos]);
            editor._history_modification_in_progress = false;
            editor.dirty = true;
        }
    },

    _redo: function redo() {
        if (editor._history_pos > 0) {
            editor._history_modification_in_progress = true;
            editor._history_pos -= 1;
            editor.load(editor.history[editor.history.length - 1 - editor._history_pos]);
            editor._history_modification_in_progress = false;
            editor.dirty = true;
        }
    },

    _save: function () {
        $("#editor-save").prop('disabled', true).prepend('<span class="fa fa-cog fa-spin"></span>');
        var dump = editor.dump();
        $.post(window.location.href, {
            'data': JSON.stringify(dump),
            'csrfmiddlewaretoken': $("input[name=csrfmiddlewaretoken]").val(),
            'background': editor.uploaded_file_id,
        }, function (data) {
            if (data.status === 'ok') {
                $("#editor-save span").remove();
                $("#editor-save").prop('disabled', false);
                editor.dirty = false;
                editor.uploaded_file_id = null;
            } else {
                alert(gettext('Saving failed.'));
            }
        }, 'json');
        return false;
    },

    _preview: function () {
        $("#preview-form input[name=data]").val(JSON.stringify(editor.dump()));
        $("#preview-form input[name=background]").val(editor.uploaded_file_id);
        $("#preview-form").get(0).submit();
    },

    _replace_pdf_file: function (url) {
        editor.pdf_url = url;
        d = editor.dump();
        editor.fabric.dispose();
        editor._load_pdf(d);
    },

    _source_show: function () {
        $("#source-textarea").text(JSON.stringify(editor.dump()));
        $("#source-container").show();
    },

    _source_close: function () {
        $("#source-container").hide();
    },

    _source_save: function () {
        editor.load(JSON.parse($("#source-textarea").val()));
        $("#source-container").hide();
    },

    _create_empty_background: function () {
        $("#loading-container, #loading-upload").show();
        $("#loading-upload .progress").show();
        $('#loading-upload .progress-bar').css('width', 0);
        $("#fileupload").prop('disabled', true);
        $(".background-button").addClass("disabled");
        $.post(window.location.href, {
            'csrfmiddlewaretoken': $("input[name=csrfmiddlewaretoken]").val(),
            'emptybackground': 'true',
            'width': $("#pdf-info-width").val(),
            'height': $("#pdf-info-height").val(),
        }, function (data) {
            if (data.status === "ok") {
                editor.uploaded_file_id = data.id;
                editor._replace_pdf_file(data.url);
            } else {
                alert(data.result.error || gettext("Error while uploading your PDF file, please try again."));
                $("#loading-container, #loading-upload").hide();
            }
            $("#fileupload").prop('disabled', false);
            $(".background-button").removeClass("disabled");
        }, 'json');
    },

    init: function () {
        editor.$pdfcv = $("#pdf-canvas");
        editor.pdf_url = editor.$pdfcv.attr("data-pdf-url");
        editor.$fcv = $("#fabric-canvas");
        editor.$cva = $("#editor-canvas-area");
        editor._load_pdf();
        $("#editor-add-qrcode, #editor-add-qrcode-lead").click(editor._add_qrcode);
        $("#editor-add-text").click(editor._add_text);
        $("#editor-add-poweredby").click(function() {editor._add_poweredby("dark")});
        editor.$cva.get(0).tabIndex = 1000;
        editor.$cva.on("keydown", editor._on_keydown);
        $("#editor-save").on("click", editor._save);
        $("#editor-preview").on("click", editor._preview);
        window.onbeforeunload = function () {
            if (editor.dirty) {
                return gettext("Do you really want to leave the editor without saving your changes?");
            }
        };
        $("#source-container").hide();


        $("#pdf-empty").on("click", editor._create_empty_background);
        $('#fileupload').fileupload({
            url: location.href,
            dataType: 'json',
            done: function (e, data) {
                if (data.result.status === "ok") {
                    editor.uploaded_file_id = data.result.id;
                    editor._replace_pdf_file(data.result.url);
                } else {
                    alert(data.result.error || gettext("Error while uploading your PDF file, please try again."));
                    $("#loading-container, #loading-upload").hide();
                }
                $("#fileupload").prop('disabled', false);
                $(".background-button").removeClass("disabled");
            },
            add: function (e, data) {
                data.formData = {
                    'csrfmiddlewaretoken': $("input[name=csrfmiddlewaretoken]").val()
                };
                $("#loading-container, #loading-upload").show();
                $("#loading-upload .progress").show();
                $('#loading-upload .progress-bar').css('width', 0);
                $("#fileupload").prop('disabled', true);
                $(".background-button").addClass("disabled");
                data.process().done(function () {
                    data.submit();
                });
            },
            progressall: function (e, data) {
                var progress = parseInt(data.loaded / data.total * 100, 10);
                $('#loading-upload .progress-bar').css('width', progress + '%');
            }
        }).prop('disabled', !$.support.fileInput).parent().addClass($.support.fileInput ? undefined : 'disabled');

        $("#toolbox input[type=number], #toolbox textarea, #toolbox input[type=text]").bind('change keydown keyup' +
            ' input', editor._update_values_from_toolbox);
        $("#toolbox input[type=number], #toolbox textarea, #toolbox input[type=text], #toolbox input[type=radio]").bind('change', editor._create_savepoint);
        $("#toolbox label.btn").bind('click change', editor._update_values_from_toolbox);
        $("#toolbox select").bind('change', editor._update_values_from_toolbox);
        $("#toolbox select").bind('change', editor._create_savepoint);
        $("#toolbox button.toggling").bind('click change', function () {
            if ($(this).is(".option")) {
                $(this).addClass("active");
                $(this).parent().siblings().find("button").removeClass("active");
            } else {
                $(this).toggleClass("active");
            }
            editor._update_values_from_toolbox();
            editor._create_savepoint();
        });
        $("#toolbox .colorpickerfield").bind('changeColor', editor._update_values_from_toolbox);
        $("#toolbox-copy").bind('click', editor._copy);
        $("#toolbox-cut").bind('click', editor._cut);
        $("#toolbox-delete").bind('click', editor._delete);
        $("#toolbox-paste").bind('click', editor._paste);
        $("#toolbox-undo").bind('click', editor._undo);
        $("#toolbox-redo").bind('click', editor._redo);
        $("#toolbox-source").bind('click', editor._source_show);
        $("#source-close").bind('click', editor._source_close);
        $("#source-save").bind('click', editor._source_save);
    }
};

$(function () {
    editor.init();
});
$(window).bind('load', editor._window_load_event);
