/*globals $, gettext, fabric, PDFJS*/
fabric.Poweredby = fabric.util.createClass(fabric.Image, {
    type: 'poweredby',

    initialize: function (options) {
        options || (options = {});

        var el = $("#poweredby-" + options.content).get(0)
        this.callSuper('initialize', el, options);
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
fabric.Imagearea = fabric.util.createClass(fabric.Rect, {
    type: 'imagearea',

    initialize: function (text, options) {
        options || (options = {});

        this.callSuper('initialize', text, options);
        this.set('label', options.label || '');
    },

    toObject: function () {
        return fabric.util.object.extend(this.callSuper('toObject'), {});
    },

    _render: function (ctx) {
        ctx.fillStyle = '#009'
        this.callSuper('_render', ctx);

        ctx.font = '12px Helvetica';
        ctx.fillStyle = '#fff';
        ctx.fillText(this.content, -this.width / 2, -this.height / 2 + 20, this.width);
    },
});
fabric.Imagearea.fromObject = function (object, callback, forceAsync) {
    return fabric.Object._fromObject('Imagearea', object, callback, forceAsync);
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
            ctx.fillText(this.content, -this.width / 2, -this.height / 2 + 20);
        } else if (!this.content || this.content === "secret") {
            ctx.fillText(gettext('Check-in QR'), -this.width / 2, -this.height / 2 + 20);
        } else {
            ctx.fillText(this.content, -this.width / 2, -this.height / 2 + 20);
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
    pdf: null,
    pdf_page: null,
    pdf_page_number: 1,
    pdf_page_count: 1,
    pdf_scale: 1,
    pdf_viewport: null,
    _history_pos: 0,
    _history_modification_in_progress: false,
    _other_page_objects: [],
    dirty: false,
    _ever_saved: false,
    pdf_url: null,
    uploaded_file_id: null,
    _window_loaded: false,
    _fabric_loaded: false,
    schema: null,

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
        var d = !objs ? JSON.parse(JSON.stringify(editor._other_page_objects)) : [];
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
                var col = (new fabric.Color(o.fill))._source;
                var bottom = editor.pdf_viewport.height - o.height - top;
                if (o.downward) {
                    bottom = editor.pdf_viewport.height - top;
                }
                d.push({
                    type: "textarea",
                    page: editor.pdf_page_number,
                    locale: $("#pdf-info-locale").val(),
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(bottom).toFixed(2),
                    fontsize: editor._px2pt(o.fontSize).toFixed(1),
                    lineheight: o.lineHeight,
                    color: col,
                    fontfamily: o.fontFamily,
                    bold: o.fontWeight === 'bold',
                    italic: o.fontStyle === 'italic',
                    width: editor._px2mm(o.width).toFixed(2),
                    downward: o.downward || false,
                    content: o.content,
                    text: o.text,
                    text_i18n: o.text_i18n || {},
                    rotation: o.angle,
                    align: o.textAlign,
                });
            } else  if (o.type === "imagearea") {
                d.push({
                    type: "imagearea",
                    page: editor.pdf_page_number,
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(editor.pdf_viewport.height - o.height * o.scaleY - top).toFixed(2),
                    height: editor._px2mm(o.height * o.scaleY).toFixed(2),
                    width: editor._px2mm(o.width * o.scaleX).toFixed(2),
                    content: o.content,
                });
            } else  if (o.type === "barcodearea") {
                d.push({
                    type: "barcodearea",
                    page: editor.pdf_page_number,
                    left: editor._px2mm(left).toFixed(2),
                    bottom: editor._px2mm(editor.pdf_viewport.height - o.height * o.scaleY - top).toFixed(2),
                    size: editor._px2mm(o.height * o.scaleY).toFixed(2),
                    content: o.content,
                    text: o.text,
                    text_i18n: o.text_i18n || {},
                    nowhitespace: o.nowhitespace || false,
                });
            } else  if (o.type === "poweredby") {
                d.push({
                    type: "poweredby",
                    page: editor.pdf_page_number,
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
        var targetPage = d.page || 1;
        if (targetPage !== editor.pdf_page_number) {
            editor._other_page_objects.push(d);
            return
        }
        if (d.type === "barcodearea") {
            o = editor._add_qrcode();
            o.content = d.content;
            o.scaleToHeight(editor._mm2px(d.size));
            o.nowhitespace = d.nowhitespace || false;
            if (d.content === "other") {
                o.text = d.text
            } else if (d.content === "other_i18n") {
                o.text_i18n = d.text_i18n
            }
        } else if (d.type === "imagearea") {
            o = editor._add_imagearea(d.content);
            o.content = d.content;
            o.set('height', editor._mm2px(d.height));
            o.set('width', editor._mm2px(d.width));
            o.set('scaleX', 1);
            o.set('scaleY', 1);
        } else if (d.type === "poweredby") {
            o = editor._add_poweredby(d.content);
            o.content = d.content;
            o.scaleToHeight(editor._mm2px(d.size));
        } else if (d.type === "textarea" || o.type === "text") {
            o = editor._add_text();
            o.set('fill', 'rgb(' + d.color[0] + ',' + d.color[1] + ',' + d.color[2] + ')');
            o.set('fontSize', editor._pt2px(d.fontsize));
            o.set('lineHeight', d.lineheight || 1);
            o.set('fontFamily', d.fontfamily);
            o.set('fontWeight', d.bold ? 'bold' : 'normal');
            o.set('fontStyle', d.italic ? 'italic' : 'normal');
            o.downward = d.downward || false;
            o.content = d.content;
            o.set('textAlign', d.align);
            if (d.rotation) {
                o.rotate(d.rotation);
            }
            if (d.content === "other") {
                o.set('text', d.text);
            } else if (d.content === "other_i18n") {
                o.text_i18n = d.text_i18n
                o.set('text', d.text_i18n[Object.keys(d.text_i18n)[0]]);
            } else if (d.content) {
                o.set('text', editor._get_text_sample(d.content));
            }
            o.set('width', editor._mm2px(d.width));  // needs to be after setText
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
        editor._other_page_objects = [];
        for (var i in data) {
            var d = data[i], o;
            editor._add_from_data(d);
        }
        editor.fabric.renderAll();
        editor._update_toolbox_values();
    },

    _get_text_sample: function (key) {
        if (key.startsWith('itemmeta:')) {
            return key.substr(9);
        } else if (key.startsWith('meta:')) {
            return key.substr(5);
        }
        return $('#toolbox-content option[value="'+key+'"], #toolbox-content option[data-old-value="'+key+'"]').attr('data-sample') || '???';
    },

    _load_page: function (page_number, dump) {
        var previous_dump = editor._fabric_loaded ? editor.dump() : [];

        // Fetch the required page
        editor.pdf.getPage(page_number).then(function (page) {
            var canvas = document.getElementById('pdf-canvas');

            var scale = editor.$cva.width() / page.getViewport({scale: 1.0}).width;
            var viewport = page.getViewport({ scale: scale });
            var outputScale = window.devicePixelRatio || 1;

            // Prepare canvas using PDF page dimensions
            var context = canvas.getContext('2d');
            context.clearRect(0, 0, canvas.width, canvas.height);
            canvas.width = Math.floor(viewport.width * outputScale);
            canvas.height = Math.floor(viewport.height * outputScale);
            canvas.style.width = Math.floor(viewport.width) + "px";
            canvas.style.height =  Math.floor(viewport.height) + "px";
            var transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;

            editor.pdf_page = page;
            editor.pdf_scale = scale;
            editor.pdf_viewport = viewport;

            // Render PDF page into canvas context
            var renderContext = {
                canvasContext: context,
                transform: transform,
                viewport: viewport,
            };
            var renderTask = page.render(renderContext);
            renderTask.promise.then(function () {
                editor.pdf_page_number = page_number
                editor._init_page_nav();

                if (dump || !editor._fabric_loaded) {
                    editor._init_fabric(dump);
                } else {
                    editor.load(previous_dump);
                }
            });
        });
    },

    _init_page_nav: function () {
        if (editor.pdf_page_count === 1) {
            $("#page_nav").hide();
        } else {
            $("#page_nav").html("");
            for (i = 1; i <= editor.pdf_page_count; i++) {
                var $li = $("<li>").addClass("nav-item");
                var $a = $("<a>").text(i).attr("href", "#").attr("data-page", i).appendTo($li);
                if (i === editor.pdf_page_number) {
                    $li.addClass("active")
                }
                $("#page_nav").append($li)
                $a.on("click", function (event) {
                    editor.fabric.discardActiveObject();
                    editor._load_page(parseInt($(this).attr("data-page")));
                    event.preventDefault();
                    return true;
                })
            }
            $("#page_nav").show();
        }
    },

    _load_pdf: function (dump) {
        // TODO: Loading indicators
        var url = editor.pdf_url;
        // TODO: Handle cross-origin issues if static files are on a different origin
        var pdfjsLib = window['pdfjs-dist/build/pdf'];
        pdfjsLib.GlobalWorkerOptions.workerSrc = editor.$pdfcv.attr("data-worker-url");

        // Asynchronous download of PDF
        var loadingTask = pdfjsLib.getDocument(url);
        loadingTask.promise.then(function (pdf) {

            editor.pdf = pdf;
            editor.pdf_page_count = pdf.numPages;
            if (editor.pdf_page_count > 10) {
                alert('Please do not upload files with more than 10 pages for performance reasons.')
            }
            editor._init_page_nav();
            editor._load_page(1, dump);
        }, function (reason) {
            var msg = gettext('The PDF background file could not be loaded for the following reason:');
            editor._error(msg + ' ' + reason);
        });
    },

    _init_fabric: function (dump) {
        editor.$fcv.get(0).width = editor.pdf_viewport.width;
        editor.$fcv.get(0).height = editor.pdf_viewport.height;
        editor.fabric = new fabric.Canvas('fabric-canvas');

        editor.fabric.on('object:modified', editor._create_savepoint);
        editor.fabric.on('object:added', editor._create_savepoint);
        editor.fabric.on('selection:cleared', editor._update_toolbox);
        editor.fabric.on('selection:created', editor._update_toolbox);
        editor.fabric.on('selection:updated', editor._update_toolbox);
        editor.fabric.on('object:modified', editor._update_toolbox_values);
        editor._update_toolbox();

        $("#toolbox-content-other").hide();
        $("#toolbox-content-other-i18n").hide();
        $("#toolbox-content-other-help").hide();
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
        editor._update_save_button();

        if ($("#loading-upload").is(":visible")) {
            $("#loading-container, #loading-upload").hide();
        }

        editor._fabric_loaded = true;
        if (editor._window_loaded) {
            editor._ready();
        }
    },

    _window_load_event: function () {
        editor._window_loaded = true;
        if (editor._fabric_loaded) {
            editor._ready();
        }
    },

    _ready: function () {
        var isOpera = (!!window.opr && !!opr.addons) || !!window.opera || navigator.userAgent.indexOf(' OPR/') >= 0;
        var isFirefox = navigator.userAgent.indexOf("Firefox") > 0;
        var isChromeBased = !!window.chrome;
        if (isChromeBased || isOpera || isFirefox) {
            $("#loading-container").hide();
            $("#loading-initial").remove();
        } else {
            $("#editor-loading").hide();
            $("#editor-start").removeClass("sr-only");
            $("#editor-start").click(function () {
                $("#loading-container").hide();
                $("#loading-initial").remove();
            });
        }
    },

    _update_toolbox_values: function () {
        var o = editor.fabric.getActiveObject();
        if (!o) {
            return;
        }
        var bottom = editor.pdf_viewport.height - o.height * o.scaleY - o.top;
        if (o.downward) {
            bottom = editor.pdf_viewport.height - o.top;
        }
        $("#toolbox-position-x").val(editor._px2mm(o.left).toFixed(2));
        $("#toolbox-position-y").val(editor._px2mm(bottom).toFixed(2));

        if (o.type === "barcodearea") {
            $("#toolbox-squaresize").val(editor._px2mm(o.height * o.scaleY).toFixed(2));
            $("#toolbox-qrwhitespace").prop("checked", o.nowhitespace || false);
        } else if (o.type === "imagearea") {
            $("#toolbox-height").val(editor._px2mm(o.height * o.scaleY).toFixed(2));
            $("#toolbox-width").val(editor._px2mm(o.width * o.scaleX).toFixed(2));
            $("#toolbox-imagecontent").val(o.content);
        } else if (o.type === "poweredby") {
            $("#toolbox-squaresize").val(editor._px2mm(o.height * o.scaleY).toFixed(2));
            $("#toolbox-poweredby-style").val(o.content);
        } else if (o.type === "text" || o.type === "textarea") {
            var col = (new fabric.Color(o.fill))._source;
            $("#toolbox-col").val("#" + ((1 << 24) + (col[0] << 16) + (col[1] << 8) + col[2]).toString(16).slice(1));
            $("#toolbox-fontsize").val(editor._px2pt(o.fontSize).toFixed(1));
            $("#toolbox-lineheight").val(o.lineHeight || 1);
            $("#toolbox-fontfamily").val(o.fontFamily);
            $("#toolbox").find("button[data-action=bold]").toggleClass('active', o.fontWeight === 'bold');
            $("#toolbox").find("button[data-action=italic]").toggleClass('active', o.fontStyle === 'italic');
            $("#toolbox").find("button[data-action=downward]").toggleClass('active', o.downward || false);
            $("#toolbox").find("button[data-action=left]").toggleClass('active', o.textAlign === 'left');
            $("#toolbox").find("button[data-action=center]").toggleClass('active', o.textAlign === 'center');
            $("#toolbox").find("button[data-action=right]").toggleClass('active', o.textAlign === 'right');
            $("#toolbox-textwidth").val(editor._px2mm(o.width).toFixed(2));
            $("#toolbox-textrotation").val((o.angle || 0.0).toFixed(1));
        }

        if (o.type === "textarea" || o.type === "barcodearea") {
            if (!o.content && o.type == "barcodearea") {
                o.content = "secret";
            }
            var $migrate_to = $("#toolbox-content option[data-old-value='" + o.content + "']");
            if ($migrate_to.length > 0) {
                $("#toolbox-content").val($migrate_to.val());
            } else {
                $("#toolbox-content").val(o.content);
            }
            $("#toolbox-content-other").toggle($("#toolbox-content").val() === "other");
            $("#toolbox-content-other-i18n").toggle($("#toolbox-content").val() === "other_i18n");
            $("#toolbox-content-other-help").toggle($("#toolbox-content").val() === "other" || $("#toolbox-content").val() === "other_i18n");
            if (o.content === "other") {
                $("#toolbox-content-other").val(o.text);
            } else if (o.content === "other_i18n") {
                $("#toolbox-content-other-i18n textarea").each(function () {
                    $(this).val(o.text_i18n[$(this).attr("lang")] || '');
                });
            } else {
                $("#toolbox-content-other").val("");
            }
        }
    },

    _update_values_from_toolbox: function (e) {
        var o = editor.fabric.getActiveObject();
        if (!o) {
            return;
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
            o.set('height', new_h);
            o.set('width', new_h);
            o.set('scaleX', 1);
            o.set('scaleY', 1);
            o.set('top', new_top)
            o.nowhitespace = $("#toolbox-qrwhitespace").prop("checked") || false;

            $("#toolbox-content-other").toggle($("#toolbox-content").val() === "other");
            $("#toolbox-content-other-i18n").toggle($("#toolbox-content").val() === "other_i18n");
            $("#toolbox-content-other-help").toggle($("#toolbox-content").val() === "other" || $("#toolbox-content").val() === "other_i18n");
            o.content = $("#toolbox-content").val();
            if ($("#toolbox-content").val() === "other") {
                if (e.target.id === "toolbox-content") {
                    // user used dropdown to switch content-type, update value with value from i18n textarea
                    $("#toolbox-content-other").val($("#toolbox-content-other-i18n textarea").val());
                }
                o.text = $("#toolbox-content-other").val();
            } else if ($("#toolbox-content").val() === "other_i18n") {
                if (e.target.id === "toolbox-content") {
                    // user used dropdown to switch content-type, update value with value from "other" textarea
                    $("#toolbox-content-other-i18n textarea").val($("#toolbox-content-other").val());
                }
                o.text_i18n = {}
                $("#toolbox-content-other-i18n textarea").each(function () {
                    o.text_i18n[$(this).attr("lang")] = $(this).val();
                });
            } else {
                o.text = editor._get_text_sample($("#toolbox-content").val());
            }
        } else if (o.type === "imagearea") {
            var new_w = editor._mm2px($("#toolbox-width").val());
            var new_h = editor._mm2px($("#toolbox-height").val());
            new_top += o.height * o.scaleY - new_h;
            o.set('height', new_h);
            o.set('width', new_w);
            o.set('scaleX', 1);
            o.set('scaleY', 1);
            o.set('top', new_top)
            o.content = $("#toolbox-imagecontent").val();
        } else if (o.type === "poweredby") {
            var new_h = Math.max(1, editor._mm2px($("#toolbox-squaresize").val()));
            new_top += o.height * o.scaleY - new_h;
            o.set('width', new_h / o.height * o.width);
            o.set('height', new_h);
            o.set('scaleX', 1);
            o.set('scaleY', 1);
            o.set('top', new_top)
            if ($("#toolbox-poweredby-style").val() !== o.content) {
                var data = editor.dump([o]);
                data[0].content = $("#toolbox-poweredby-style").val();
                var newo = editor._add_from_data(data[0]);
                editor.fabric.remove(o);
                editor.fabric.discardActiveObject();
                editor.fabric.setActiveObject(newo);
            }
        } else if (o.type === "textarea" || o.type === "text") {
            o.set('fill', $("#toolbox-col").val());
            o.set('fontSize', editor._pt2px($("#toolbox-fontsize").val()));
            o.set('lineHeight', $("#toolbox-lineheight").val() || 1);
            o.set('fontFamily', $("#toolbox-fontfamily").val());
            o.set('fontWeight', $("#toolbox").find("button[data-action=bold]").is('.active') ? 'bold' : 'normal');
            o.set('fontStyle', $("#toolbox").find("button[data-action=italic]").is('.active') ? 'italic' : 'normal');
            var align = $("#toolbox-align").find(".active").attr("data-action");
            if (align) {
                o.set('textAlign', align);
            }
            o.downward = $("#toolbox").find("button[data-action=downward]").is('.active');
            o.rotate(parseFloat($("#toolbox-textrotation").val()));
            $("#toolbox-content-other").toggle($("#toolbox-content").val() === "other");
            $("#toolbox-content-other-i18n").toggle($("#toolbox-content").val() === "other_i18n");
            $("#toolbox-content-other-help").toggle($("#toolbox-content").val() === "other" || $("#toolbox-content").val() === "other_i18n");
            o.content = $("#toolbox-content").val();
            if ($("#toolbox-content").val() === "other") {
                if (e.target.id === "toolbox-content") {
                    // user used dropdown to switch content-type, update value with value from i18n textarea
                    $("#toolbox-content-other").val($("#toolbox-content-other-i18n textarea").val());
                }
                o.set('text', $("#toolbox-content-other").val());
            } else if ($("#toolbox-content").val() === "other_i18n") {
                if (e.target.id === "toolbox-content") {
                    // user used dropdown to switch content-type, update value with value from "other" textarea
                    $("#toolbox-content-other-i18n textarea").val($("#toolbox-content-other").val());
                }
                o.text_i18n = {}
                $("#toolbox-content-other-i18n textarea").each(function () {
                    o.text_i18n[$(this).attr("lang")] = $(this).val();
                });
                o.set('text', $("#toolbox-content-other-i18n textarea").first().val());
            } else {
                o.set('text', editor._get_text_sample($("#toolbox-content").val()));
            }
            o.set('width', editor._mm2px($("#toolbox-textwidth").val()));
        }

        // empty text-inputs if not in use
        if ($("#toolbox-content").val() !== "other") {
            $("#toolbox-content-other").val("");
        }
        if ($("#toolbox-content").val() !== "other_i18n") {
            $("#toolbox-content-other-i18n textarea").val("");
        }

        o.setCoords();
        editor.fabric.renderAll();
    },

    _update_toolbox: function () {
        var selected = editor.fabric.getActiveObjects();
        if (selected.length > 1) {
            $("#toolbox").attr("data-type", "group");
            $("#toolbox-heading").text(gettext("Group of objects"));
        } else if (selected.length == 1) {
            var o = selected[0];
            $("#toolbox").attr("data-type", o.type);
            if (o.type === "textarea" || o.type === "text") {
                $("#toolbox-heading").text(gettext("Text object"));
            } else if (o.type === "barcodearea") {
                $("#toolbox-heading").text(gettext("Barcode area"));
            } else if (o.type === "imagearea") {
                $("#toolbox-heading").text(gettext("Image area"));
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
            editor._paper_size_warning();
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
            content: 'event_name',
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
            height: 629,
            width: 1024,
            lockRotation: true,
            content: content
        });
        rect.scaleToHeight(126);
        rect.setControlsVisibility({'mtr': false, 'mb': false, 'mt': false, 'mr': false, 'ml': false});
        editor.fabric.add(rect);
        editor._create_savepoint();
        return rect;
    },

    _add_imagearea: function () {
        var rect = new fabric.Imagearea({
            left: 100,
            top: 100,
            width: 100,
            height: 100,
            lockRotation: true,
            fill: '#666',
            content: '',
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
            fill: '#666',
            content: $(this).attr("data-content"),
            text: '',
            nowhitespace: true,
        });
        rect.setControlsVisibility({'mtr': false, 'mb': false, 'mt': false, 'mr': false, 'ml': false});
        editor.fabric.add(rect);
        editor._create_savepoint();
        return rect;
    },

    _cut: function () {
        editor._history_modification_in_progress = true;
        var thing = editor.fabric.getActiveObject();
        if (thing.type === "activeSelection") {
            editor.clipboard = editor.dump(thing._objects);
            thing.forEachObject(function (o) {
                editor.fabric.remove(o);
            });
            editor.fabric.remove(thing);
        } else {
            editor.clipboard = editor.dump([thing]);
            editor.fabric.remove(thing);
        }
        editor.fabric.discardActiveObject();
        editor._history_modification_in_progress = false;
        editor._create_savepoint();
    },

    _copy: function () {
        editor._history_modification_in_progress = true;
        var thing = editor.fabric.getActiveObject();
        if (thing.type === "activeSelection") {
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
            editor.clipboard[i].page = editor.pdf_page_number;
            objs.push(editor._add_from_data(editor.clipboard[i]));
        }
        editor.fabric.discardActiveObject();
        if (editor.clipboard.length > 1) {
            var selection = new fabric.ActiveSelection(objs, {canvas: editor.fabric});
            editor.fabric.setActiveObject(selection);
        } else {
            editor.fabric.setActiveObject(objs[0]);
        }
        editor._history_modification_in_progress = false;
        editor._create_savepoint();
    },

    _delete: function () {
        var thing = editor.fabric.getActiveObject();
        if (thing.type === "activeSelection") {
            thing.forEachObject(function (o) {
                editor.fabric.remove(o);
            });
            editor.fabric.remove(thing);
            editor.fabric.discardActiveObject();
        } else {
            editor.fabric.remove(thing);
            editor.fabric.discardActiveObject();
        }
        editor._create_savepoint();
    },

    _on_keydown: function (e) {
        var step = e.shiftKey ? editor._mm2px(10) : editor._mm2px(1);
        var thing = editor.fabric.getActiveObject();
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
            case 8:  /* Backspace */
            case 46:  /* Delete */
                editor._delete();
                break;
            case 65:  /* A */
                if (e.ctrlKey || e.metaKey) {
                    editor._selectAll();
                }
                break;
            case 89:  /* Y */
                if (e.ctrlKey || e.metaKey) {
                    editor._redo();
                }
                break;
            case 90:  /* Z */
                if (e.ctrlKey || e.metaKey) {
                    editor._undo();
                }
                break;
            case 88:  /* X */
                if (e.ctrlKey || e.metaKey) {
                    editor._cut();
                }
                break;
            case 86:  /* V */
                if (e.ctrlKey || e.metaKey) {
                    editor._paste();
                }
                break;
            case 67:  /* C */
                if (e.ctrlKey || e.metaKey) {
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
        editor._update_save_button();
    },

    _selectAll: function () {
        var selection = new fabric.ActiveSelection(editor.fabric._objects, {canvas: editor.fabric});
        editor.fabric.setActiveObject(selection);
    },

    _undo: function undo() {
        if (editor._history_pos < editor.history.length - 1) {
            editor._history_modification_in_progress = true;
            editor._history_pos += 1;
            editor.fabric.clear().renderAll();
            editor.load(editor.history[editor.history.length - 1 - editor._history_pos]);
            editor._history_modification_in_progress = false;
            editor.dirty = true;
            editor._update_save_button();
        }
    },

    _redo: function redo() {
        if (editor._history_pos > 0) {
            editor._history_modification_in_progress = true;
            editor._history_pos -= 1;
            editor.load(editor.history[editor.history.length - 1 - editor._history_pos]);
            editor._history_modification_in_progress = false;
            editor.dirty = true;
            editor._update_save_button();
        }
    },

    _update_save_button() {
        if ($("#editor-save span").prop("disabled")) {
            // Currently saving
            return;
        }
        if (editor.dirty || !editor._ever_saved) {
            $("#editor-save").removeClass("btn-success").addClass("btn-primary").find(".fa").attr("class", "fa fa-fw fa-save");
        } else {
            $("#editor-save").addClass("btn-success").removeClass("btn-primary").find(".fa").attr("class", "fa fa-fw fa-check");
        }
    },

    _save: function () {
        $("#editor-save").prop('disabled', true).removeClass("btn-success").addClass("btn-primary").find(".fa").attr("class", "fa fa-fw fa-cog fa-spin");
        var dump = editor.dump();
        var payload = {
            'data': JSON.stringify(dump),
            'csrfmiddlewaretoken': $("input[name=csrfmiddlewaretoken]").val(),
            'background': editor.uploaded_file_id,
        };
        if ($("#pdf-info-name").length > 0) {
            payload.name = $("#pdf-info-name").val();
        }
        $.post(window.location.href, payload, function (data) {
            if (data.status === 'ok') {
                $("#editor-save").prop('disabled', false);
                editor.dirty = false;
                editor.uploaded_file_id = null;
                editor._ever_saved = true;
                editor._update_save_button();
            } else {
                alert(gettext('Saving failed.'));
            }
        }, 'json');
        return false;
    },

    _preview: function (e) {
        $("#preview-form input[name=data]").val(JSON.stringify(editor.dump()));
        $("#preview-form input[name=background]").val(editor.uploaded_file_id);
        if (!e || !e.target.form) $("#preview-form").get(0).submit();
    },

    _replace_pdf_file: function (url) {
        editor.pdf_url = url;
        d = editor.dump();
        editor.fabric.dispose();
        editor._load_pdf(d);
        $(".background-download-button").attr("href", url);
    },

    _source_show: function () {
        $("#source-textarea").text(JSON.stringify(editor.dump()));
        $("#source-container").show();
    },

    _source_close: function () {
        $("#source-container").hide();
    },

    _source_save: function () {
        try {
            var Ajv = window.ajv2020
            var ajv = new Ajv()
            var validate = ajv.compile(editor.schema)
            var data = JSON.parse($("#source-textarea").val())
            var valid = validate(data)

            if (!valid) {
                console.log(validate.errors)
                alert("Invalid input syntax. If you're familiar with this, check out the developer console for a full " +
                      "error log. Otherwise, please contact support.")
            } else {
                editor.load(data);
                $("#source-container").hide();
            }
        } catch (e) {
            console.error(e)
            alert("Parsing error. If you're familiar with this, check out the developer console for a full " +
                "error log. Otherwise, please contact support.")
        }
    },

    _create_empty_background: function () {
        editor._paper_size_warning();
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
        editor.dirty = true;
    },

    _paper_size_warning: function () {
        var warn = editor.pdf_viewport && (
            Math.abs(parseFloat($("#pdf-info-height").val()) - editor._px2mm(editor.pdf_viewport.height)) > 0.001 ||
            Math.abs(parseFloat($("#pdf-info-width").val()) - editor._px2mm(editor.pdf_viewport.width)) > 0.001
        );
        $("#pdf-empty").toggleClass("btn-primary", warn).toggleClass("btn-default", !warn);
    },

    init: function () {
        editor.$pdfcv = $("#pdf-canvas");
        editor.pdf_url = editor.$pdfcv.attr("data-pdf-url");
        editor.$fcv = $("#fabric-canvas");
        editor.$cva = $("#editor-canvas-area");
        editor._load_pdf();
        $("#editor-add-qrcode, #editor-add-qrcode-lead, #editor-add-qrcode-other").click(editor._add_qrcode);
        $("#editor-add-image").click(editor._add_imagearea);
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
                    editor.dirty = true;
                    editor._update_save_button();
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

        $("#toolbox input[type=number], #toolbox textarea, #toolbox input[type=text], #toolbox input[type=checkbox]").bind('change keydown keyup' +
            ' input', editor._update_values_from_toolbox);
        $("#toolbox input[type=number], #toolbox textarea, #toolbox input[type=text], #toolbox input[type=checkbox], #toolbox input[type=radio]").bind('change', editor._create_savepoint);
        $("#toolbox label.btn").bind('click change', editor._update_values_from_toolbox);
        $("#toolbox select").bind('change', editor._update_values_from_toolbox);
        $("#toolbox select").bind('change', editor._create_savepoint);
        $("#toolbox button.toggling").bind('click change', function (e) {
            if ($(this).is(".option")) {
                $(this).addClass("active");
                $(this).parent().siblings().find("button").removeClass("active");
            } else {
                $(this).toggleClass("active");
            }
            editor._update_values_from_toolbox(e);
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
        $("#pdf-info-name").bind('change', function () {
            editor.dirty = true;
            editor._update_save_button();
        });
        $("#pdf-info-width, #pdf-info-height").bind('change', editor._paper_size_warning);

        $.getJSON($("#schema-url").text(), function (data) {
            editor.schema = data;
        })
    }
};

$(function () {
    editor.init();
});
$(window).bind('load', editor._window_load_event);
