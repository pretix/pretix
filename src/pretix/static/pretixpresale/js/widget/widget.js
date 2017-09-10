/*global siteglobals, module*/
/* PRETIX WIDGET BEGINS HERE */
/* This is embedded in an isolation wrapper that exposes siteglobals as the global
   scope. */

var Vue = module.exports;

var I18N_STRINGS = {  // TODO: Translate
    'en': {
        'sold_out': 'Sold out',
        'reserved': 'Reserved',
        'free': 'FREE',
        'price_from': 'from $1 $2',
        'tax_incl': 'incl. $1% $2',
        'tax_plus': 'plus $1% $2',
        'quota_left': 'currently available: $1',
        'voucher_required': 'Only available with a voucher',
        'order_min': 'minimum amount to order: %s',
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

    '_getJSON': function (endpoint, callback) {
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
        };
        xhr.send(null);
    }
};

var site_is_secure = function () {
    // TODO: Forbid iframe on insecure pages
    return /https.*/.test(document.location.protocol)
};

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
                return 'variation_' + this.item.id + '_' + this.variation.avail;
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
        + '{{ priceline }}'
        + '<small class="pretix-widget-pricebox-tax" v-if="price.rate != \'0.00\' && price.gross != \'0.00\'">'
        + '{{ taxline }}'
        + '</small>'
        + '</div>'),
    props: {
        price: Object
    },
    computed: {
        priceline: function () {
            if (this.price.gross === "0.00") {
                return strings.free;
            } else if (this.$root.display_net_prices) {
                return this.$root.currency + " " + this.price.net;
            } else {
                return this.$root.currency + " " + this.price.gross;
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
        + '<pricebox :price="variation.price"></pricebox>'
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
        + '<div class="pretix-widget-item-row">'

        + '<div class="pretix-widget-item-info-col">'
        // TODO: Picture
        + '<div class="pretix-widget-item-title-and-description">'
        + '<strong class="pretix-widget-item-title">{{ item.name }}</strong>'
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
        + '<pricebox :price="item.price" v-if="!item.has_variations"></pricebox>'
        + '<div class="pretix-widget-pricebox" v-if="item.has_variations">{{ pricerange }}</div>'
        + '</div>'
        + '<div class="pretix-widget-item-availability-col">'
        + '<span v-if="item.has_variations">See variations</span>'
        + '<availbox v-if="!item.has_variations" :item="item"></availbox>'
        + '</div>'

        + '<div class="pretix-widget-clear"></div>'
        + '</div>'

        + '<div class="pretix-widget-item-variations" v-if="item.has_variations">'
        + '<variation v-for="variation in item.variations" :variation="variation" :item="item" :key="variation.id">'
        + '</variation>'
        + '</div>'

        + '</div>'),
    props: {
        item: Object
    },
    computed: {
        classObject: function () {
            return {
                'pretix-widget-item': true,
                'pretix-widget-item-with-variations': this.item.has_variations
            }
        },
        min_order_str: function () {
            return strings["order_min"].replace("%s", this.item.order_min);
        },
        quota_left_str: function () {
            return strings["quota_left"].replace("$1", this.item.avail[1]);
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
    template: ('<div class="pretix-widget">'
        + '<form>'
        + '<category v-for="category in this.$root.categories" :category="category" :key="category.id"></category>'
        + '<div class="pretix-widget-clear"></div>'
        + '<div class="pretix-widget-attribution">'
        + strings.poweredby
        + '</div>'
        + '</form>'
        + '</div>'),
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
            }
        },
        created: function () {
            api._getJSON(event_url + 'widget/product_list', function (data) {
                app.categories = data.items_by_category;
                app.currency = data.currency;
                app.display_net_prices = data.display_net_prices;
            })
        },
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
