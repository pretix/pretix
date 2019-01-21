/*global siteglobals, module, lang, django*/
/* PRETIX WIDGET BEGINS HERE */
/* This is embedded in an isolation wrapper that exposes siteglobals as the global
   scope. */

window.PretixWidget = {
    'build_widgets': true,
    'widget_data': {}
};

var Vue = module.exports;

var strings = {
    'sold_out': django.pgettext('widget', 'Sold out'),
    'buy': django.pgettext('widget', 'Buy'),
    'reserved': django.pgettext('widget', 'Reserved'),
    'free': django.pgettext('widget', 'FREE'),
    'price_from': django.pgettext('widget', 'from %(currency)s %(price)s'),
    'tax_incl': django.pgettext('widget', 'incl. %(rate)s% %(taxname)s'),
    'tax_plus': django.pgettext('widget', 'plus %(rate)s% %(taxname)s'),
    'quota_left': django.pgettext('widget', 'currently available: %s'),
    'voucher_required': django.pgettext('widget', 'Only available with a voucher'),
    'order_min': django.pgettext('widget', 'minimum amount to order: %s'),
    'exit': django.pgettext('widget', 'Close ticket shop'),
    'loading_error': django.pgettext('widget', 'The ticket shop could not be loaded.'),
    'cart_error': django.pgettext('widget', 'The cart could not be created. Please try again later'),
    'waiting_list': django.pgettext('widget', 'Waiting list'),
    'cart_exists': django.pgettext('widget', 'You currently have an active cart for this event. If you select more' +
        ' products, they will be added to your existing cart.'),
    'resume_checkout': django.pgettext('widget', 'Resume checkout'),
    'poweredby': django.pgettext('widget', '<a href="https://pretix.eu" target="_blank" rel="noopener">event' +
        ' ticketing powered by pretix</a>'),
    'redeem_voucher': django.pgettext('widget', 'Redeem a voucher'),
    'redeem': django.pgettext('widget', 'Redeem'),
    'voucher_code': django.pgettext('widget', 'Voucher code'),
    'close': django.pgettext('widget', 'Close'),
    'continue': django.pgettext('widget', 'Continue'),
    'variations': django.pgettext('widget', 'See variations'),
};

var setCookie = function (cname, cvalue, exdays) {
    var d = new Date();
    d.setTime(d.getTime() + (exdays * 24 * 60 * 60 * 1000));
    var expires = "expires=" + d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
};
var getCookie = function (name) {
    var value = "; " + document.cookie;
    var parts = value.split("; " + name + "=");
    if (parts.length == 2) return parts.pop().split(";").shift() || null;
    else return null;
};

/* HTTP API Call helpers */
var api = {
    '_getXHR': function () {
        try {
            return new window.XMLHttpRequest();
        } catch (e) {
            // explicitly bubble up the exception if not found
            return new window.ActiveXObject('Microsoft.XMLHTTP');
        }
    },

    '_getJSON': function (endpoint, callback, err_callback) {
        var xhr = api._getXHR();
        xhr.open("GET", endpoint, true);
        xhr.onload = function (e) {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    callback(JSON.parse(xhr.responseText));
                } else {
                    console.error(xhr.statusText);
                }
            }
        };
        xhr.onerror = function (e) {
            console.error(xhr.statusText);
            err_callback(xhr, e);
        };
        xhr.send(null);
    },

    '_postFormJSON': function (endpoint, form, callback, err_callback) {
        var params = [].filter.call(form.elements, function (el) {
            return (el.type !== 'checkbox' && el.type !== 'radio') || el.checked;
        })
            .filter(function (el) {
                return !!el.name && !!el.value;
            })
            .filter(function (el) {
                return !el.disabled;
            })
            .map(function (el) {
                return encodeURIComponent(el.name) + '=' + encodeURIComponent(el.value);
            }).join('&');

        var xhr = api._getXHR();
        xhr.open("POST", endpoint, true);
        xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
        xhr.onload = function (e) {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    callback(JSON.parse(xhr.responseText));
                } else {
                    console.error(xhr.statusText);
                }
            }
        };
        xhr.onerror = function (e) {
            console.error(xhr.statusText);
            err_callback(xhr, e);
        };
        xhr.send(params);
    }
};

var makeid = function (length) {
    var text = "";
    var possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    for (var i = 0; i < length; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }

    return text;
};

var site_is_secure = function () {
    return /https.*/.test(document.location.protocol)
};

var widget_id = makeid(16);

/* Vue Components */
Vue.component('availbox', {
    template: ('<div class="pretix-widget-availability-box">'
        + '<div class="pretix-widget-availability-unavailable" v-if="item.require_voucher">'
        + '<small>' + strings.voucher_required + '</small>'
        + '</div>'
        + '<div class="pretix-widget-availability-unavailable"'
        + '       v-if="!item.require_voucher && avail[0] < 100 && avail[0] > 10">'
        + strings.reserved
        + '</div>'
        + '<div class="pretix-widget-availability-gone" '
        + '       v-if="!item.require_voucher && avail[0] <= 10">'
        + strings.sold_out
        + '</div>'
        + '<div class="pretix-widget-waiting-list-link"'
        + '     v-if="waiting_list_show">'
        + '<a :href="waiting_list_url" target="_blank" @click="$root.open_link_in_frame">' + strings.waiting_list + '</a>'
        + '</div>'
        + '<div class="pretix-widget-availability-available" v-if="!item.require_voucher && avail[0] === 100">'
        + '<label class="pretix-widget-item-count-single-label" v-if="order_max === 1">'
        + '<input type="checkbox" value="1" v-bind:name="input_name">'
        + '</label>'
        + '<input type="number" class="pretix-widget-item-count-multiple" placeholder="0" min="0"'
        + '       :value="($root.itemnum == 1 && !item.has_variations) ? 1 : false" v-bind:max="order_max" v-bind:name="input_name"'
        + '       v-if="order_max !== 1">'
        + '</div>'
        + '</div>'),
    props: {
        item: Object,
        variation: Object
    },
    computed: {
        input_name: function () {
            if (this.item.has_variations) {
                return 'variation_' + this.item.id + '_' + this.variation.id;
            } else {
                return 'item_' + this.item.id;
            }
        },
    order_max: function () {
            return this.item.has_variations ? this.variation.order_max : this.item.order_max;
        },
        avail: function () {
            return this.item.has_variations ? this.variation.avail : this.item.avail;
        },
        waiting_list_show: function () {
            return this.avail[0] < 100 && this.$root.waiting_list_enabled;
        },
        waiting_list_url: function () {
            if (this.item.has_variations) {
                return this.$root.event_url + 'w/' + widget_id + '/waitinglist/?item=' + this.item.id + '&var=' + this.variation.id;
            } else {
                return this.$root.event_url + 'w/' + widget_id + '/waitinglist/?item=' + this.item.id;
            }
        }
    }
});
Vue.component('pricebox', {
    template: ('<div class="pretix-widget-pricebox">'
        + '<span v-if="!free_price && !original_price">{{ priceline }}</span>'
        + '<span v-if="!free_price && original_price">'
        + '<del class="pretix-widget-pricebox-original-price">{{ original_line }}</del> '
        + '<ins class="pretix-widget-pricebox-new-price">{{ priceline }}</ins></span>'
        + '<div v-if="free_price">'
        + '{{ $root.currency }} '
        + '<input type="number" class="pretix-widget-pricebox-price-input" placeholder="0" '
        + '       :min="display_price" :value="display_price" :name="field_name"'
        + '       step="any">'
        + '</div>'
        + '<small class="pretix-widget-pricebox-tax" v-if="price.rate != \'0.00\' && price.gross != \'0.00\'">'
        + '{{ taxline }}'
        + '</small>'
        + '</div>'),
    props: {
        price: Object,
        free_price: Boolean,
        field_name: String,
        original_price: String
    },
    computed: {
        display_price: function () {
            if (this.$root.display_net_prices) {
                return floatformat(parseFloat(this.price.net), 2);
            } else {
                return floatformat(parseFloat(this.price.gross), 2);
            }
        },
        original_line: function () {
            return this.$root.currency + " " + floatformat(parseFloat(this.original_price), 2);
        },
        priceline: function () {
            if (this.price.gross === "0.00") {
                return strings.free;
            } else {
                return this.$root.currency + " " + this.display_price;
            }
        },
        taxline: function () {
            if (this.$root.display_net_prices) {
                return django.interpolate(strings.tax_plus, {
                    'rate': autofloatformat(this.price.rate, 2),
                    'taxname': this.price.name
                }, true);
            } else {
                return django.interpolate(strings.tax_incl, {
                    'rate': autofloatformat(this.price.rate, 2),
                    'taxname': this.price.name
                }, true);
            }
        }
    }
});
Vue.component('variation', {
    template: ('<div class="pretix-widget-variation">'
        + '<div class="pretix-widget-item-row">'

        + '<div class="pretix-widget-item-info-col">'
        + '<div class="pretix-widget-item-title-and-description">'
        + '<strong class="pretix-widget-item-title">{{ variation.value }}</strong>'
        + '<div class="pretix-widget-item-description" v-if="variation.description" v-html="variation.description"></div>'
        + '<p class="pretix-widget-item-meta" '
        + '   v-if="!variation.has_variations && variation.avail[1] !== null && variation.avail[0] === 100">'
        + '<small>{{ quota_left_str }}</small>'
        + '</p>'
        + '</div>'
        + '</div>'

        + '<div class="pretix-widget-item-price-col">'
        + '<pricebox :price="variation.price" :free_price="item.free_price" :original_price="item.original_price"'
        + '          :field_name="\'price_\' + item.id + \'_\' + variation.id" v-if="$root.showPrices">'
        + '</pricebox>'
        + '<span v-if="!$root.showPrices">&nbsp;</span>'
        + '</div>'
        + '<div class="pretix-widget-item-availability-col">'
        + '<availbox :item="item" :variation="variation"></availbox>'
        + '</div>'

        + '<div class="pretix-widget-clear"></div>'
        + '</div>'
        + '</div>'),
    props: {
        variation: Object,
        item: Object,
    },
    computed: {
        quota_left_str: function () {
            return django.interpolate(strings["quota_left"], [this.variation.avail[1]]);
        },
    }
});
Vue.component('item', {
    template: ('<div v-bind:class="classObject">'
        + '<div class="pretix-widget-item-row pretix-widget-main-item-row">'

        + '<div class="pretix-widget-item-info-col">'
        + '<img :src="item.picture" v-if="item.picture" class="pretix-widget-item-picture">'
        + '<div class="pretix-widget-item-title-and-description">'
        + '<a v-if="item.has_variations && show_toggle" class="pretix-widget-item-title" href="#"'
        + '   @click.prevent="expand">'
        + '{{ item.name }}'
        + '</a>'
        + '<strong v-else class="pretix-widget-item-title">{{ item.name }}</strong>'
        + '<div class="pretix-widget-item-description" v-if="item.description" v-html="item.description"></div>'
        + '<p class="pretix-widget-item-meta" v-if="item.order_min && item.order_min > 1">'
        + '<small>{{ min_order_str }}</small>'
        + '</p>'
        + '<p class="pretix-widget-item-meta" '
        + '    v-if="!item.has_variations && item.avail[1] !== null && item.avail[0] === 100">'
        + '<small>{{ quota_left_str }}</small>'
        + '</p>'
        + '</div>'
        + '</div>'

        + '<div class="pretix-widget-item-price-col">'
        + '<pricebox :price="item.price" :free_price="item.free_price" v-if="!item.has_variations && $root.showPrices"'
        + '          :field_name="\'price_\' + item.id" :original_price="item.original_price">'
        + '</pricebox>'
        + '<div class="pretix-widget-pricebox" v-if="item.has_variations && $root.showPrices">{{ pricerange }}</div>'
        + '<span v-if="!$root.showPrices">&nbsp;</span>'
        + '</div>'
        + '<div class="pretix-widget-item-availability-col">'
        + '<a v-if="show_toggle" href="#" @click.prevent="expand">'+ strings.variations + '</a>'
        + '<availbox v-if="!item.has_variations" :item="item"></availbox>'
        + '</div>'

        + '<div class="pretix-widget-clear"></div>'
        + '</div>'

        + '<div :class="varClasses" v-if="item.has_variations">'
        + '<variation v-for="variation in item.variations" :variation="variation" :item="item" :key="variation.id">'
        + '</variation>'
        + '</div>'

        + '</div>'),
    props: {
        item: Object,
    },
    data: function () {
        return {
            expanded: this.$root.show_variations_expanded
        };
    },
    methods: {
        expand: function () {
            this.expanded = !this.expanded;
        }
    },
    computed: {
        classObject: function () {
            return {
                'pretix-widget-item': true,
                'pretix-widget-item-with-picture': !!this.item.picture,
                'pretix-widget-item-with-variations': this.item.has_variations
            }
        },
        varClasses: function () {
            return {
                'pretix-widget-item-variations': true,
                'pretix-widget-item-variations-expanded': this.expanded,
            }
        },
        min_order_str: function () {
            return django.interpolate(strings["order_min"], [this.item.order_min]);
        },
        quota_left_str: function () {
            return django.interpolate(strings["quota_left"], [this.item.avail[1]]);
        },
        show_toggle: function () {
            return this.item.has_variations && !this.$root.show_variations_expanded;
        },
        pricerange: function () {
            if (this.item.min_price !== this.item.max_price || this.item.free_price) {
                return django.interpolate(strings.price_from, {
                    'currency': this.$root.currency,
                    'price': floatformat(this.item.min_price, 2)
                }, true);
            } else if (this.item.min_price === "0.00" && this.item.max_price === "0.00") {
                return strings.free;
            } else {
                return this.$root.currency + " " + floatformat(this.item.min_price, 2);
            }
        },
    }
});
Vue.component('category', {
    template: ('<div class="pretix-widget-category">'
        + '<h3 class="pretix-widget-category-name" v-if="category.name">{{ category.name }}</h3>'
        + '<div class="pretix-widget-category-description" v-if="category.description" v-html="category.description">'
        + '</div>'
        + '<div class="pretix-widget-category-items">'
        + '<item v-for="item in category.items" :item="item" :key="item.id"></item>'
        + '</div>'
        + '</div>'),
    props: {
        category: Object
    }
});

var shared_methods = {
    buy: function (event) {
        if (this.$root.useIframe) {
            event.preventDefault();
        } else {
            return;
        }
        if (this.$root.is_button && this.$root.items.length === 0) {
            this.resume();
        } else {
            var url = this.$root.formTarget + "&locale=" + lang + "&ajax=1";
            this.$root.overlay.frame_loading = true;

            this.async_task_interval = 100;
            api._postFormJSON(url, this.$refs.form, this.buy_callback, this.buy_error_callback);
        }
    },
    buy_error_callback: function (xhr, data) {
        this.$root.overlay.error_message = strings['cart_error'];
        this.$root.overlay.frame_loading = false;
    },
    buy_check_error_callback: function (xhr, data) {
        if (xhr.status == 200 || (xhr.status >= 400 && xhr.status < 500)) {
            this.$root.overlay.error_message = strings['cart_error'];
            this.$root.overlay.frame_loading = false;
        } else {
            this.async_task_timeout = window.setTimeout(this.buy_check, 1000);
        }
    },
    buy_callback: function (data) {
        if (data.redirect) {
            var iframe = this.$root.overlay.$children[0].$refs['frame-container'].children[0];
            this.$root.cart_id = data.cart_id;
            setCookie(this.$root.cookieName, data.cart_id, 30);
            if (data.redirect.substr(0, 1) === '/') {
                data.redirect = this.$root.event_url.replace(/^([^\/]+:\/\/[^\/]+)\/.*$/, "$1") + data.redirect;
            }
            var url = data.redirect;
            if (url.indexOf('?')) {
                url = url + '&iframe=1&locale=' + lang + '&take_cart_id=' + this.$root.cart_id;
            } else {
                url = url + '?iframe=1&locale=' + lang + '&take_cart_id=' + this.$root.cart_id;
            }
            if (data.success === false) {
                url = url.replace(/checkout\/start/g, "");
                this.$root.overlay.error_message = data.message;
                if (data.has_cart) {
                    this.$root.overlay.error_url_after = url;
                }
                this.$root.overlay.frame_loading = false;
            } else {
                iframe.src = url;
            }
        } else {
            this.async_task_id = data.async_id;
            if (data.check_url) {
                this.async_task_check_url = this.$root.event_url.replace(/^([^\/]+:\/\/[^\/]+)\/.*$/, "$1") + data.check_url;
            }
            this.async_task_timeout = window.setTimeout(this.buy_check, this.async_task_interval);
            this.async_task_interval = 250;
        }
    },
    buy_check: function () {
        api._getJSON(this.async_task_check_url, this.buy_callback, this.buy_check_error_callback);
    },
    redeem: function (event) {
        if (this.$root.useIframe) {
            event.preventDefault();
        } else {
            return;
        }
        var redirect_url = this.$root.voucherFormTarget + '&voucher=' + this.voucher + '&subevent=' + this.$root.subevent;
        if (this.$root.widget_data) {
            redirect_url += '&widget_data=' + escape(this.$root.widget_data_json);
        }
        var iframe = this.$root.overlay.$children[0].$refs['frame-container'].children[0];
        this.$root.overlay.frame_loading = true;
        iframe.src = redirect_url;
    },
    resume: function () {
        var redirect_url = this.$root.event_url + 'w/' + widget_id + '/?iframe=1&locale=' + lang;
        if (this.$root.cart_id) {
            redirect_url += '&take_cart_id=' + this.$root.cart_id;
        }
        if (this.$root.widget_data) {
            redirect_url += '&widget_data=' + escape(this.$root.widget_data_json);
        }
        if (this.$root.useIframe) {
            var iframe = this.$root.overlay.$children[0].$refs['frame-container'].children[0];
            this.$root.overlay.frame_loading = true;
            iframe.src = redirect_url;
        } else {
            window.open(redirect_url);
        }
    },
};

var shared_widget_data = function () {
    return {
        async_task_id: null,
        async_task_check_url: null,
        async_task_timeout: null,
        async_task_interval: 100,
        voucher: null,
    }
};

var shared_loading_fragment = (
    '<div class="pretix-widget-loading" v-show="$root.loading > 0">'
    + '<svg width="128" height="128" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path class="pretix-widget-primary-color" d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
    + '</div>'
);

var shared_iframe_fragment = (
    '<div :class="frameClasses">'
    + '<div class="pretix-widget-frame-loading" v-show="$root.frame_loading">'
    + '<svg width="256" height="256" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path class="pretix-widget-primary-color" d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
    + '</div>'
    + '<div class="pretix-widget-frame-inner" ref="frame-container" v-show="$root.frame_shown">'
    + '<iframe frameborder="0" width="650px" height="650px" @load="iframeLoaded" '
    + '        :name="$root.parent.widget_id" src="about:blank" v-once>'
    + 'Please enable frames in your browser!'
    + '</iframe>'
    + '<div class="pretix-widget-frame-close"><a href="#" @click.prevent="close">X</a></div>'
    + '</div>'
    + '</div>'
);

var shared_alert_fragment = (
    '<div :class="alertClasses">'
    + '<transition name="bounce">'
    + '<div class="pretix-widget-alert-box" v-if="$root.error_message">'
    + '<p>{{ $root.error_message }}</p>'
    + '<p><button v-if="$root.error_url_after" @click.prevent="errorContinue">' + strings.continue + '</button>'
    + '<button v-else @click.prevent="errorClose">' + strings.close + '</button></p>'
    + '</div>'
    + '</transition>'
    + '<svg width="64" height="64" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg" class="pretix-widget-alert-icon"><path style="fill:#ffffff;" d="M 599.86438,303.72882 H 1203.5254 V 1503.4576 H 599.86438 Z" /><path class="pretix-widget-primary-color" d="M896 128q209 0 385.5 103t279.5 279.5 103 385.5-103 385.5-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103zm128 1247v-190q0-14-9-23.5t-22-9.5h-192q-13 0-23 10t-10 23v190q0 13 10 23t23 10h192q13 0 22-9.5t9-23.5zm-2-344l18-621q0-12-10-18-10-8-24-8h-220q-14 0-24 8-10 6-10 18l17 621q0 10 10 17.5t24 7.5h185q14 0 23.5-7.5t10.5-17.5z"/></svg>'
    + '</div>'
);

Vue.component('pretix-overlay', {
    template: ('<div class="pretix-widget-overlay">'
        + shared_iframe_fragment
        + shared_alert_fragment
        + '</div>'
    ),
    computed: {
        frameClasses: function () {
            return {
                'pretix-widget-frame-holder': true,
                'pretix-widget-frame-shown': this.$root.frame_shown || this.$root.frame_loading,
            };
        },
        alertClasses: function () {
            return {
                'pretix-widget-alert-holder': true,
                'pretix-widget-alert-shown': this.$root.error_message,
            };
        },
    },
    methods: {
        errorClose: function () {
            this.$root.error_message = null;
            this.$root.error_url_after = null;
        },
        errorContinue: function () {
            var iframe = this.$refs['frame-container'].children[0];
            iframe.src = this.$root.error_url_after;
            this.$root.frame_loading = true;
            this.$root.error_message = null;
            this.$root.error_url_after = null;
        },
        close: function () {
            this.$root.frame_shown = false;
            this.$root.parent.reload();
        },
        iframeLoaded: function () {
            if (this.$root.frame_loading) {
                this.$root.frame_loading = false;
                this.$root.frame_shown = true;
            }
        }
    }
});

Vue.component('pretix-widget', {
    template: ('<div class="pretix-widget-wrapper">'
        + '<div class="pretix-widget">'
        + shared_loading_fragment
        + '<form method="post" :action="$root.formTarget" ref="form" target="_blank">'
        + '<input type="hidden" name="_voucher_code" :value="$root.voucher_code" v-if="$root.voucher_code">'
        + '<input type="hidden" name="subevent" :value="$root.subevent" />'
        + '<input type="hidden" name="widget_data" :value="$root.widget_data_json" />'
        + '<div class="pretix-widget-error-message" v-if="$root.error">{{ $root.error }}</div>'
        + '<div class="pretix-widget-info-message pretix-widget-clickable"'
        + '     v-if="$root.cart_exists">'
        + '<button @click.prevent="resume" class="pretix-widget-resume-button" type="button">'
        + strings['resume_checkout']
        + '</button>'
        + strings['cart_exists']
        + '<div class="pretix-widget-clear"></div>'
        + '</div>'
        + '<category v-for="category in this.$root.categories" :category="category" :key="category.id"></category>'
        + '<div class="pretix-widget-action" v-if="$root.display_add_to_cart">'
        + '<button @click="buy" type="submit">' + strings.buy + '</button>'
        + '</div>'
        + '</form>'
        + '<form method="get" :action="$root.voucherFormTarget" target="_blank" '
        + '      v-if="$root.vouchers_exist && !$root.disable_vouchers && !$root.voucher_code">'
        + '<div class="pretix-widget-voucher">'
        + '<h3 class="pretix-widget-voucher-headline">'+ strings['redeem_voucher'] +'</h3>'
        + '<div class="pretix-widget-voucher-input-wrap">'
        + '<input class="pretix-widget-voucher-input" type="text" v-model="voucher" name="voucher" placeholder="'+strings.voucher_code+'">'
        + '</div>'
        + '<input type="hidden" name="subevent" :value="$root.subevent" />'
        + '<input type="hidden" name="locale" value="' + lang + '" />'
        + '<div class="pretix-widget-voucher-button-wrap">'
        + '<button @click="redeem">' + strings.redeem + '</button>'
        + '</div>'
        + '</div>'
        + '</form>'
        + '<div class="pretix-widget-clear"></div>'
        + '<div class="pretix-widget-attribution">'
        + strings.poweredby
        + '</div>'
        + '</div>'
        + '</div>'
        + '</div>'
    ),
    data: shared_widget_data,
    methods: shared_methods,
});

Vue.component('pretix-button', {
    template: ('<div class="pretix-widget-wrapper">'
        + '<div class="pretix-widget-button-container">'
        + '<form method="post" :action="$root.formTarget" ref="form" target="_blank">'
        + '<input type="hidden" name="_voucher_code" :value="$root.voucher_code" v-if="$root.voucher_code">'
        + '<input type="hidden" name="subevent" :value="$root.subevent" />'
        + '<input type="hidden" name="widget_data" :value="$root.widget_data_json" />'
        + '<input type="hidden" v-for="item in $root.items" :name="item.item" :value="item.count" />'
        + '<button class="pretix-button" @click="buy">{{ $root.button_text }}</button>'
        + '</form>'
        + '<div class="pretix-widget-clear"></div>'
        + '</div>'
        + '</div>'
        + '</div>'
    ),
    data: shared_widget_data,
    methods: shared_methods,
});

/* Function to create the actual Vue instances */

var shared_root_methods = {
    open_link_in_frame: function (event) {
        if (this.$root.useIframe) {
            event.preventDefault();
            var url = event.target.attributes.href.value;
            if (url.indexOf('?')) {
                url += '&iframe=1';
            } else {
                url += '?iframe=1';
            }
            this.$root.overlay.$children[0].$refs['frame-container'].children[0].src = url;
            this.$root.overlay.frame_loading = true;
        } else {
            return;
        }
    },
    reload: function () {
        var url;
        if (this.$root.subevent) {
            url = this.$root.event_url + this.$root.subevent + '/widget/product_list?lang=' + lang;
        } else {
            url = this.$root.event_url + 'widget/product_list?lang=' + lang;
        }
        var cart_id = getCookie(this.cookieName);
        if (this.$root.voucher_code) {
            url += '&voucher=' + escape(this.$root.voucher_code);
        }
        if (cart_id) {
            url += "&cart_id=" + cart_id;
        }
        var root = this.$root;
        api._getJSON(url, function (data) {
            root.categories = data.items_by_category;
            root.currency = data.currency;
            root.display_net_prices = data.display_net_prices;
            root.error = data.error;
            root.display_add_to_cart = data.display_add_to_cart;
            root.waiting_list_enabled = data.waiting_list_enabled;
            root.show_variations_expanded = data.show_variations_expanded;
            root.cart_id = cart_id;
            root.cart_exists = data.cart_exists;
            root.vouchers_exist = data.vouchers_exist;
            root.itemnum = data.itemnum;
            if (root.loading > 0) {
                root.loading--;
            }
        }, function (error) {
            root.categories = [];
            root.currency = '';
            root.error = strings['loading_error'];
            if (root.loading > 0) {
                root.loading--;
            }
        });
    }
};

var shared_root_computed = {
    cookieName: function () {
        return "pretix_widget_" + this.event_url.replace(/[^a-zA-Z0-9]+/g, "_");
    },
    voucherFormTarget: function () {
        var form_target = this.event_url + 'w/' + widget_id + '/redeem?iframe=1&locale=' + lang;
        if (getCookie(this.cookieName)) {
            form_target += "&take_cart_id=" + getCookie(this.cookieName);
        }
        if (this.subevent) {
            form_target += "&subevent=" + this.subevent;
        }
        return form_target;
    },
    formTarget: function () {
        var checkout_url = "/" + this.event_url.replace(/^[^\/]+:\/\/([^\/]+)\//, "") + "w/" + widget_id + "/";
        if (!this.$root.cart_exists) {
            checkout_url += "checkout/start";
        }
        var form_target = this.event_url + 'w/' + widget_id + '/cart/add?iframe=1&next=' + encodeURIComponent(checkout_url);
        if (getCookie(this.cookieName)) {
            form_target += "&take_cart_id=" + getCookie(this.cookieName);
        }
        return form_target
    },
    useIframe: function () {
        return Math.min(screen.width, window.innerWidth) >= 800 && (this.skip_ssl || site_is_secure());
    },
    showPrices: function () {
        var has_priced = false;
        var cnt_items = 0;
        for (var i = 0; i < this.categories.length; i++) {
            for (var j = 0; j < this.categories[i].items.length; j++) {
                var item = this.categories[i].items[j];
                if (item.has_variations) {
                    cnt_items += item.variations.length;
                    has_priced = true;
                } else {
                    cnt_items++;
                    has_priced = has_priced || item.price.gross != "0.00";
                }
            }
        }
        return has_priced || cnt_items > 1;
    },
    widget_data_json: function () {
        return JSON.stringify(this.widget_data);
    }
};

var create_overlay = function (app) {
    var elem = document.createElement('pretix-overlay');
    document.body.appendChild(elem);

    var framechild = new Vue({
        el: elem,
        data: function () {
            return {
                parent: app,
                frame_loading: false,
                frame_shown: false,
                error_url_after: null,
                error_message: null,
            }
        },
        methods: {
        }
    });
    app.$root.overlay = framechild;
};

function get_ga_client_id(tracking_id) {
    if (typeof ga === "undefined") {
        return null;
    }
    try {
        var trackers = ga.getAll();
        var i, len;
        for (i = 0, len = trackers.length; i < len; i += 1) {
            if (trackers[i].get('trackingId') === tracking_id) {
                return trackers[i].get('clientId');
            }
        }
    } catch (e) {
    }
    return null;
}

var create_widget = function (element) {
    var event_url = element.attributes.event.value;
    if (!event_url.match(/\/$/)) {
        event_url += "/";
    }
    var voucher = element.attributes.voucher ? element.attributes.voucher.value : null;
    var subevent = element.attributes.subevent ? element.attributes.subevent.value : null;
    var skip_ssl = element.attributes["skip-ssl-check"] ? true : false;
    var disable_vouchers = element.attributes["disable-vouchers"] ? true : false;
    var widget_data = JSON.parse(JSON.stringify(window.PretixWidget.widget_data));
    for (var i = 0; i < element.attributes.length; i++) {
        var attrib = element.attributes[i];
        if (attrib.name.match(/^data-.*$/)) {
            widget_data[attrib.name.replace(/^data-/, '')] = attrib.value;
        }
    }

    if (element.tagName !== "pretix-widget") {
        element.innerHTML = "<pretix-widget></pretix-widget>";
    }

    var app = new Vue({
        el: element,
        data: function () {
            return {
                event_url: event_url,
                subevent: subevent,
                is_button: false,
                categories: null,
                currency: null,
                voucher_code: voucher,
                display_net_prices: false,
                show_variations_expanded: false,
                skip_ssl: skip_ssl,
                error: null,
                display_add_to_cart: false,
                widget_data: widget_data,
                loading: 1,
                widget_id: 'pretix-widget-' + widget_id,
                vouchers_exist: false,
                disable_vouchers: disable_vouchers,
                cart_exists: false,
                itemcount: 0,
                overlay: null
            }
        },
        created: function () {
            this.reload();
        },
        computed: shared_root_computed,
        methods: shared_root_methods
    });
    create_overlay(app);
    return app;
};

var create_button = function (element) {
    var event_url = element.attributes.event.value;
    if (!event_url.match(/\/$/)) {
        event_url += "/";
    }
    var voucher = element.attributes.voucher ? element.attributes.voucher.value : null;
    var subevent = element.attributes.subevent ? element.attributes.subevent.value : null;
    var raw_items = element.attributes.items ? element.attributes.items.value : "";
    var skip_ssl = element.attributes["skip-ssl-check"] ? true : false;
    var button_text = element.innerHTML;
    var widget_data = JSON.parse(JSON.stringify(window.PretixWidget.widget_data));
    for (var i = 0; i < element.attributes.length; i++) {
        var attrib = element.attributes[i];
        if (attrib.name.match(/^data-.*$/)) {
            widget_data[attrib.name.replace(/^data-/, '')] = attrib.value;
        }
    }

    if (element.tagName !== "pretix-button") {
        element.innerHTML = "<pretix-button>" + element.innerHTML + "</pretix-button>";
    }

    var itemsplit = raw_items.split(",");
    var items = [];
    for (var i = 0; i < itemsplit.length; i++) {
        if (itemsplit[i].indexOf("=") > 0 ) {
            var splitthis = itemsplit[i].split("=");
            items.push({'item': splitthis[0], 'count': splitthis[1]})
        }
    }

    var app = new Vue({
        el: element,
        data: function () {
            return {
                event_url: event_url,
                subevent: subevent,
                is_button: true,
                skip_ssl: skip_ssl,
                voucher_code: voucher,
                items: items,
                error: null,
                widget_data: widget_data,
                widget_id: 'pretix-widget-' + widget_id,
                button_text: button_text
            }
        },
        created: function () {
        },
        computed: shared_root_computed,
        methods: shared_root_methods
    });
    create_overlay(app);
    return app;
};

/* Find all widgets on the page and render them */
widgetlist = [];
buttonlist = [];
window.PretixWidget.buildWidgets = function () {
    document.createElement("pretix-widget");
    document.createElement("pretix-button");
    docReady(function () {
        var widgets = document.querySelectorAll("pretix-widget, div.pretix-widget-compat");
        var wlength = widgets.length;
        for (var i = 0; i < wlength; i++) {
            var widget = widgets[i];
            widgetlist.push(create_widget(widget));
        }

        var buttons = document.querySelectorAll("pretix-button, div.pretix-button-compat");
        var blength = buttons.length;
        for (var i = 0; i < blength; i++) {
            var button = buttons[i];
            buttonlist.push(create_button(button));
        }
    });
};
if (typeof window.pretixWidgetCallback !== "undefined") {
    window.pretixWidgetCallback();
}
if (window.PretixWidget.build_widgets) {
    window.PretixWidget.buildWidgets();
}

/* Set a global variable for debugging. In DEBUG mode, siteglobals will be window, otherwise it will be something
   unnamed. */
siteglobals.pretixwidget_debug = {
    'Vue': Vue,
    'widgets': widgetlist,
    'buttons': buttonlist
};
