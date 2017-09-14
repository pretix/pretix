/*global siteglobals, module*/
/* PRETIX WIDGET BEGINS HERE */
/* This is embedded in an isolation wrapper that exposes siteglobals as the global
   scope. */

var Vue = module.exports;

var I18N_STRINGS = {  // TODO: Translate
    'en': {
        'sold_out': 'Sold out',
        'buy': 'Buy',
        'reserved': 'Reserved',
        'free': 'FREE',
        'price_from': 'from $1 $2',
        'tax_incl': 'incl. $1% $2',
        'tax_plus': 'plus $1% $2',
        'quota_left': 'currently available: $1',
        'voucher_required': 'Only available with a voucher',
        'order_min': 'minimum amount to order: %s',
        'exit': 'Close ticket shop',
        'loading_error': 'The ticket shop could not be loaded.',
        'poweredby': 'ticketing powered by <a href="https://pretix.eu" target="_blank">pretix</a>'
    }
};

var strings = I18N_STRINGS['en'];

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
            err_callback(e);
        };
        xhr.send(null);
    }
};

var makeid = function (length) {
    var text = "";
    var possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    for (var i = 0; i < length; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }

    return text;
}

var site_is_secure = function () {
    // TODO: Forbid iframe on insecure pages
    return /https.*/.test(document.location.protocol)
};

var widget_id = makeid(16);

/* Vue Components */
Vue.component('availbox', {
    template: ('<div class="pretix-widget-availability-box">'
        + '<div class="pretix-widget-availability-unavailable" v-if="item.require_voucher">'
        + strings.voucher_required
        + '</div>'
        + '<div class="pretix-widget-availability-unavailable"' +
        '       v-if="!item.require_voucher && avail[0] < 100 && avail[0] > 10">'
        + strings.reserved
        + '</div>'
        + '<div class="pretix-widget-availability-gone" ' +
        '       v-if="!item.require_voucher && avail[0] <= 10">'
        + strings.sold_out
        + '</div>'
        + '<div class="pretix-widget-availability-available" v-if="!item.require_voucher && avail[0] === 100">'
        + '<label class="pretix-widget-item-count-single-label" v-if="order_max === 1">'
        + '<input type="checkbox" value="1" v-bind:name="input_name">'
        + '</label>'
        + '<input type="number" class="pretix-widget-item-count-multiple" placeholder="0" min="0"'
        + '       v-bind:max="order_max" v-bind:name="input_name" v-if="order_max !== 1">'
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
    }
});
Vue.component('pricebox', {
    template: ('<div class="pretix-widget-pricebox">'
        + '<span v-if="!free_price">{{ priceline }}</span>'
        + '<span v-if="free_price">'
        + '{{ $root.currency }} '
        + '<input type="number" class="pretix-widget-pricebox-price-input" placeholder="0" '
        + '       :min="display_price" :value="display_price" :name="field_name"'
        + '       step="any">'
        + '</span>'
        + '<small class="pretix-widget-pricebox-tax" v-if="price.rate != \'0.00\' && price.gross != \'0.00\'">'
        + '{{ taxline }}'
        + '</small>'
        + '</div>'),
    props: {
        price: Object,
        free_price: Boolean,
        field_name: String
    },
    computed: {
        display_price: function () {
            if (this.$root.display_net_prices) {
                return this.price.net;
            } else {
                return this.price.gross;
            }
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
                return strings.tax_plus.replace(/\$1/, this.price.rate).replace(/\$2/, this.price.name);
            } else {
                return strings.tax_incl.replace(/\$1/, this.price.rate).replace(/\$2/, this.price.name);
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
        + '<pricebox :price="variation.price" :free_price="item.free_price"'
        + '          :field_name="\'price_\' + item.id + \'_\' + variation.id">'
        + '</pricebox>'
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
            return strings["quota_left"].replace("$1", this.variation.avail[1]);
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
        +  '{{ item.name }}'
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
        + '<pricebox :price="item.price" :free_price="item.free_price" v-if="!item.has_variations"'
        + '          :field_name="\'price_\' + item.id">'
        + '</pricebox>'
        + '<div class="pretix-widget-pricebox" v-if="item.has_variations">{{ pricerange }}</div>'
        + '</div>'
        + '<div class="pretix-widget-item-availability-col">'
        + '<a v-if="show_toggle" href="#" @click.prevent="expand">See variations</a>'
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
            return strings["order_min"].replace("%s", this.item.order_min);
        },
        quota_left_str: function () {
            return strings["quota_left"].replace("$1", this.item.avail[1]);
        },
        show_toggle: function () {
            return this.item.has_variations && !this.$root.show_variations_expanded;
        },
        pricerange: function () {
            if (this.item.min_price !== this.item.max_price || this.item.free_price) {
                return strings.price_from.replace(/\$1/, this.$root.currency).replace(/\$2/, this.item.min_price)
            } else if (this.item.min_price === "0.00" && this.item.max_price === "0.00") {
                return strings.free;
            } else {
                return this.$root.currency + " " + this.item.min_price;
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
Vue.component('pretix-widget', {
    template: ('<div>'
        + '<div class="pretix-widget">'
        + '<div class="pretix-widget-loading" v-show="$root.loading > 0">'
        + '<svg width="128" height="128" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
        + '</div>'
        + '<form method="post" :action="$root.formTarget" :target="$root.widget_id">'
        + '<div class="pretix-widget-error-message" v-if="$root.error">{{ $root.error }}</div>'
        + '<category v-for="category in this.$root.categories" :category="category" :key="category.id"></category>'
        + '<div class="pretix-widget-action" v-if="$root.display_add_to_cart">'
        + '<button @click="buy">' + strings.buy + '</button>'
        + '</div>'
        + '<div class="pretix-widget-clear"></div>'
        + '<div class="pretix-widget-attribution">'
        + strings.poweredby
        + '</div>'
        + '</form>'
        + '</div>'
        + '<div :class="frameClasses">'
        + '<div class="pretix-widget-frame-inner" ref="frame-container" v-once>'
        + '<iframe frameborder="0" width="650px" height="650px" '
        + '        :name="$root.widget_id" :src="$root.formTarget">'
        + 'Please enable frames in your browser!'
        + '</iframe>'
        + '<div class="pretix-widget-frame-close"><a href="#" @click.prevent="close">X</a></div>'
        + '</div>'
        + '</div>'
        + '</div>'
    ),
    data: function () {
        return {
            frame_shown: false,
        }
    },
    methods: {
        buy: function () {
            this.frame_shown = true;
        },
        close: function () {
            this.frame_shown = false;
        },
    },
    computed: {
        frameClasses: function () {
            return {
                'pretix-widget-frame-holder': true,
                'pretix-widget-frame-shown': this.frame_shown,
            };
        },
    }
});

/* Function to create the actual Vue instances */
var create_widget = function (element) {
    var event_url = element.attributes.event.value;
    if (!event_url.match(/\/$/)) {
        event_url += "/";
    }

    var app = new Vue({
        el: element,
        data: function () {
            return {
                event_url: event_url,
                categories: null,
                currency: null,
                display_net_prices: false,
                show_variations_expanded: false,
                error: null,
                display_add_to_cart: false,
                loading: 1,
                language: element.attributes.event.lang,
                widget_id: 'pretix-widget-' + widget_id
            }
        },
        created: function () {
            var url = event_url + 'widget/product_list?lang=' + this.language;
            api._getJSON(url, function (data) {
                app.categories = data.items_by_category;
                app.currency = data.currency;
                app.display_net_prices = data.display_net_prices;
                app.error = data.error;
                app.display_add_to_cart = data.display_add_to_cart;
                app.show_variations_expanded = data.show_variations_expanded;
                app.loading--;
            }, function (error) {
                app.categories = [];
                app.currency = '';
                app.error = strings['loading_error'];
                app.loading--;
            });
        },
        computed: {
            formTarget: function () {
                var checkout_url = "/" + this.$root.event_url.replace(/^[^\/]+:\/\/([^\/]+)\//, "") + "checkout/start";
                return this.$root.event_url + 'cart/create?next=' + checkout_url;
            }
        }
    });
    return app;
};

/* Find all widgets on the page and render them */
widgetlist = [];
document.createElement("pretix-widget");
docReady(function () {
    var widgets = document.querySelectorAll("pretix-widget");
    var wlength = widgets.length;

    for (var i = 0; i < wlength; i++) {
        var widget = widgets[i];
        widgetlist.push(create_widget(widget));
    }
});

/* Set a global variable for debugging. In DEBUG mode, siteglobals will be window, otherwise it will be something
   unnamed. */
siteglobals.pretixwidget = {
    'Vue': Vue,
    'widgets': widgetlist
};
