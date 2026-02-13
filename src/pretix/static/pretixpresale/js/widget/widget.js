/*global siteglobals, module, lang, django*/
/* PRETIX WIDGET BEGINS HERE */
/* This is embedded in an isolation wrapper that exposes siteglobals as the global
   scope. */

window.PretixWidget = {
    'build_widgets': true,
    'widget_data': {
        'referer': location.href
    }
};

var Vue = module.exports;

var strings = {
    'quantity': django.pgettext('widget', 'Quantity'),
    'quantity_dec': django.pgettext('widget', 'Decrease quantity'),
    'quantity_inc': django.pgettext('widget', 'Increase quantity'),
    'filter_events_by': django.pgettext('widget', 'Filter events by'),
    'filter': django.pgettext('widget', 'Filter'),
    'price': django.pgettext('widget', 'Price'),
    'original_price': django.pgettext('widget', 'Original price: %s'),
    'new_price': django.pgettext('widget', 'New price: %s'),
    'select': django.pgettext('widget', 'Select'),
    'select_item': django.pgettext('widget', 'Select %s'),
    'select_variant': django.pgettext('widget', 'Select variant %s'),
    'sold_out': django.pgettext('widget', 'Sold out'),
    'buy': django.pgettext('widget', 'Buy'),
    'register': django.pgettext('widget', 'Register'),
    'reserved': django.pgettext('widget', 'Reserved'),
    'free': django.pgettext('widget', 'FREE'),
    'price_from': django.pgettext('widget', 'from %(currency)s %(price)s'),
    'image_of': django.pgettext('widget', 'Image of %s'),
    'tax_incl': django.pgettext('widget', 'incl. %(rate)s% %(taxname)s'),
    'tax_plus': django.pgettext('widget', 'plus %(rate)s% %(taxname)s'),
    'tax_incl_mixed': django.pgettext('widget', 'incl. taxes'),
    'tax_plus_mixed': django.pgettext('widget', 'plus taxes'),
    'quota_left': django.pgettext('widget', 'currently available: %s'),
    'unavailable_require_voucher': django.pgettext('widget', 'Only available with a voucher'),
    'unavailable_available_from': django.pgettext('widget', 'Not yet available'),
    'unavailable_available_until': django.pgettext('widget', 'Not available anymore'),
    'unavailable_active': django.pgettext('widget', 'Currently not available'),
    'unavailable_hidden_if_item_available': django.pgettext('widget', 'Not yet available'),
    'order_min': django.pgettext('widget', 'minimum amount to order: %s'),
    'exit': django.pgettext('widget', 'Close ticket shop'),
    'loading_error': django.pgettext('widget', 'The ticket shop could not be loaded.'),
    'loading_error_429': django.pgettext('widget', 'There are currently a lot of users in this ticket shop. Please ' +
        'open the shop in a new tab to continue.'),
    'open_new_tab': django.pgettext('widget', 'Open ticket shop'),
    'checkout': django.pgettext('widget', 'Checkout'),
    'cart_error': django.pgettext('widget', 'The cart could not be created. Please try again later'),
    'cart_error_429': django.pgettext('widget', 'We could not create your cart, since there are currently too many ' +
        'users in this ticket shop. Please click "Continue" to retry in a new tab.'),
    'waiting_list': django.pgettext('widget', 'Waiting list'),
    'cart_exists': django.pgettext('widget', 'You currently have an active cart for this event. If you select more' +
        ' products, they will be added to your existing cart.'),
    'resume_checkout': django.pgettext('widget', 'Resume checkout'),
    'redeem_voucher': django.pgettext('widget', 'Redeem a voucher'),
    'redeem': django.pgettext('widget', 'Redeem'),
    'voucher_code': django.pgettext('widget', 'Voucher code'),
    'close': django.pgettext('widget', 'Close'),
    'close_checkout': django.pgettext('widget', 'Close checkout'),
    'cancel_blocked': django.pgettext('widget', 'You cannot cancel this operation. Please wait for loading to finish.'),
    'continue': django.pgettext('widget', 'Continue'),
    'variations': django.pgettext('widget', 'Show variants'),
    'hide_variations': django.pgettext('widget', 'Hide variants'),
    'back_to_list': django.pgettext('widget', 'Choose a different event'),
    'back_to_dates': django.pgettext('widget', 'Choose a different date'),
    'back': django.pgettext('widget', 'Back'),
    'next_month': django.pgettext('widget', 'Next month'),
    'previous_month': django.pgettext('widget', 'Previous month'),
    'next_week': django.pgettext('widget', 'Next week'),
    'previous_week': django.pgettext('widget', 'Previous week'),
    'show_seating': django.pgettext('widget', 'Open seat selection'),
    'seating_plan_waiting_list': django.pgettext('widget', 'Some or all ticket categories are currently sold out. If you want, you can add yourself to the waiting list. We will then notify if seats are available again.'),
    'load_more': django.pgettext('widget', 'Load more'),
    'days': {
        'MO': django.gettext('Mo'),
        'TU': django.gettext('Tu'),
        'WE': django.gettext('We'),
        'TH': django.gettext('Th'),
        'FR': django.gettext('Fr'),
        'SA': django.gettext('Sa'),
        'SU': django.gettext('Su'),
        'MONDAY': django.gettext('Monday'),
        'TUESDAY': django.gettext('Tuesday'),
        'WEDNESDAY': django.gettext('Wednesday'),
        'THURSDAY': django.gettext('Thursday'),
        'FRIDAY': django.gettext('Friday'),
        'SATURDAY': django.gettext('Saturday'),
        'SUNDAY': django.gettext('Sunday'),
    },
    'months': {
        '01': django.gettext('January'),
        '02': django.gettext('February'),
        '03': django.gettext('March'),
        '04': django.gettext('April'),
        '05': django.gettext('May'),
        '06': django.gettext('June'),
        '07': django.gettext('July'),
        '08': django.gettext('August'),
        '09': django.gettext('September'),
        '10': django.gettext('October'),
        '11': django.gettext('November'),
        '12': django.gettext('December'),
    }
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

var padNumber = function(number, size) {
    var s = String(number);
    while (s.length < (size || 2)) {s = "0" + s;}
    return s;
};

var getISOWeeks = function (y) {
    var d, isLeap;

    d = new Date(y, 0, 1);
    isLeap = new Date(y, 1, 29).getMonth() === 1;

    //check for a Jan 1 that's a Thursday or a leap year that has a
    //Wednesday jan 1. Otherwise it's 52
    return d.getDay() === 4 || isLeap && d.getDay() === 3 ? 53 : 52
};

/* HTTP API Call helpers */
var api = {
    '_getJSON': function (endpoint, callback, err_callback) {
        var xhr = new window.XMLHttpRequest();
        xhr.open("GET", endpoint, true);
        xhr.onload = function (e) {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    callback(JSON.parse(xhr.responseText), xhr);
                } else {
                    err_callback(xhr, e);
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

        var xhr = new window.XMLHttpRequest();
        xhr.open("POST", endpoint, true);
        xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
        xhr.onload = function (e) {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    callback(JSON.parse(xhr.responseText));
                } else {
                    err_callback(xhr, e);
                }
            }
        };
        xhr.onerror = function (e) {
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
        + '<div class="pretix-widget-availability-unavailable"'
        + '     v-if="item.current_unavailability_reason === \'require_voucher\'">'
        + '<small><a :href="voucher_jump_link" v-bind:aria-describedby="aria_labelledby">{{unavailability_reason_message}}</a></small>'
        + '</div>'
        + '<div class="pretix-widget-availability-unavailable"'
        + '     v-else-if="unavailability_reason_message">'
        + '<small>{{unavailability_reason_message}}</small>'
        + '</div>'
        + '<div class="pretix-widget-availability-unavailable"'
        + '     v-else-if="avail[0] < 100 && avail[0] > 10">'
        + strings.reserved
        + '</div>'
        + '<div class="pretix-widget-availability-gone" '
        + '     v-else-if="avail[0] <= 10">'
        + strings.sold_out
        + '</div>'
        + '<div class="pretix-widget-waiting-list-link"'
        + '     v-if="waiting_list_show && !unavailability_reason_message">'
        + '<a :href="waiting_list_url" target="_blank" @click="$root.open_link_in_frame">' + strings.waiting_list + '</a>'
        + '</div>'
        + '<div class="pretix-widget-availability-available" v-if="!unavailability_reason_message && avail[0] === 100">'
        + '<label class="pretix-widget-item-count-single-label pretix-widget-btn-checkbox" v-if="order_max === 1">'
        + '<input ref="quantity" type="checkbox" value="1" :name="input_name"'
        + '       v-bind:aria-label="label_select_item"'
        + '>'
        + '<span class="pretix-widget-icon-cart" aria-hidden="true"></span> ' + strings.select
        + '</label>'
        + '<div class="pretix-widget-item-count-group" v-else role="group" v-bind:aria-label="item.name">'
        + '<button type="button" @click.prevent.stop="on_step" data-step="-1" v-bind:data-controls="\'input_\' + input_name" class="pretix-widget-btn-default pretix-widget-item-count-dec" v-bind:aria-label="dec_label"><span>-</span></button>'
        + '<input ref="quantity" type="number" inputmode="numeric" pattern="\d*" class="pretix-widget-item-count-multiple" placeholder="0" min="0"'
        + '       :max="order_max" :name="input_name" :id="\'input_\' + input_name"'
        + '       v-bind:aria-labelledby="aria_labelledby"'
        + '       >'
        + '<button type="button" @click.prevent.stop="on_step" data-step="1" v-bind:data-controls="\'input_\' + input_name" class="pretix-widget-btn-default pretix-widget-item-count-inc" v-bind:aria-label="inc_label"><span>+</span></button>'
        + '</div>'
        + '</div>'
        + '</div>'),
    props: {
        item: Object,
        variation: Object
    },
    mounted: function() {
        if (!this.$root.cart_exists && this.$root.itemnum === 1 && (!this.$root.categories[0].items[0].has_variations || this.$root.categories[0].items[0].variations.length < 2) && !this.$root.has_seating_plan ? 1 : 0) {
            this.$refs.quantity.value = 1;    
            if (this.order_max === 1) {
                this.$refs.quantity.checked = true;
            }
        }
    },
    computed: {
        voucher_jump_link: function () {
            return '#' + this.$root.html_id + '-voucher-input';
        },
        aria_labelledby: function () {
            return this.$root.html_id + '-item-label-' + this.item.id;
        },
        dec_label: function () {
            return '- ' + (this.item.has_variations ? this.variation.value : this.item.name) + ': ' + strings.quantity_dec;
        },
        inc_label: function () {
            return '+ ' + (this.item.has_variations ? this.variation.value : this.item.name) + ': ' + strings.quantity_inc;
        },
        unavailability_reason_message: function () {
            var reason = this.item.current_unavailability_reason || this.variation?.current_unavailability_reason;
            if (reason) {
                return strings["unavailable_" + reason] || reason;
            }
            return "";
        },
        label_select_item: function () {
            return this.item.has_variations
                ? strings.select_variant.replace("%s", this.variation.value)
                : strings.select_item.replace("%s", this.item.name)
        },
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
            return this.avail[0] < 100 && this.$root.waiting_list_enabled && this.item.allow_waitinglist;
        },
        waiting_list_url: function () {
            var u = this.$root.target_url + 'w/' + widget_id + '/waitinglist/?locale=' + lang + '&item=' + this.item.id 
            if (this.item.has_variations) {
                u += '&var=' + this.variation.id
            }
            if (this.$root.subevent) {
                u += '&subevent=' + this.$root.subevent
            }
            u += '&widget_data=' + encodeURIComponent(this.$root.widget_data_json) + this.$root.consent_parameter
            return u
        }
    },
    methods: {
        on_step: function (e) {
            var t = e.target.tagName == 'BUTTON' ? e.target : e.target.closest('button');
            var step = parseFloat(t.getAttribute("data-step"));
            var controls = document.getElementById(t.getAttribute("data-controls"));
            this.$refs.quantity.value = Math.max(controls.min, Math.min(controls.max || Number.MAX_SAFE_INTEGER, (parseInt(this.$refs.quantity.value || "0")) + step));
            this.$refs.quantity.dispatchEvent(new CustomEvent("change", {
                bubbles: true,
            }));
        }
    }
});
Vue.component('pricebox', {
    template: ('<div class="pretix-widget-pricebox">'
        + '<span v-if="!free_price && !original_price" v-html="priceline"></span>'
        + '<span v-if="!free_price && original_price">'
        + '<del class="pretix-widget-pricebox-original-price" v-bind:aria-label="original_price_aria_label" v-html="original_line"></del> '
        + '<ins class="pretix-widget-pricebox-new-price" v-bind:aria-label="new_price_aria_label" v-html="priceline"></ins></span>'
        + '<div v-if="free_price">'
        + '<span class="pretix-widget-pricebox-currency" :id="price_box_id">{{ $root.currency }}</span> '
        + '<input type="number" class="pretix-widget-pricebox-price-input" placeholder="0" '
        + '       :min="display_price_nonlocalized" :value="suggested_price_nonlocalized" :name="field_name"'
        + '       step="any" v-bind:aria-labelledby="aria_labelledby" v-bind:aria-describedby="price_desc_id">'
        + '</div>'
        + '<small class="pretix-widget-pricebox-tax" :id="price_desc_id" v-if="price.rate != \'0.00\' && price.gross != \'0.00\'">'
        + '{{ taxline }}'
        + '</small>'
        + '</div>'),
    props: {
        price: Object,
        free_price: Boolean,
        field_name: String,
        suggested_price: Object,
        original_price: String,
        mandatory_priced_addons: Boolean,
        item_id: Number,
    },
    methods: {
        stripHTML: function (s) {
            var div = document.createElement('div');
            div.innerHTML = s;
            return div.textContent || div.innerText || '';
        },
    },
    computed: {
        aria_labelledby: function () {
            return [
                this.$root.html_id + '-item-label-' + this.item_id,
                this.price_box_id
            ].join(" ");
        },
        price_box_id: function () {
            return this.$root.html_id + '-item-pricebox-' + this.item_id;
        },
        price_desc_id: function () {
            return this.$root.html_id + '-item-pricedesc-' + this.item_id;
        },
        display_price: function () {
            if (this.$root.display_net_prices) {
                return floatformat(parseFloat(this.price.net), 2);
            } else {
                return floatformat(parseFloat(this.price.gross), 2);
            }
        },
        display_price_nonlocalized: function () {
            if (this.$root.display_net_prices) {
                return parseFloat(this.price.net).toFixed(2);
            } else {
                return parseFloat(this.price.gross).toFixed(2);
            }
        },
        suggested_price_nonlocalized: function () {
            var price = this.suggested_price;
            if (price === null) {
                price = this.price;
            }
            if (this.$root.display_net_prices) {
                return parseFloat(price.net).toFixed(2);
            } else {
                return parseFloat(price.gross).toFixed(2);
            }
        },
        original_price_aria_label: function () {
            return django.interpolate(strings.original_price, [this.stripHTML(this.original_line)]);
        },
        new_price_aria_label: function () {
            return django.interpolate(strings.new_price, [this.stripHTML(this.priceline)]);
        },
        original_line: function () {
            return '<span class="pretix-widget-pricebox-currency">' + this.$root.currency + "</span> " + floatformat(parseFloat(this.original_price), 2);
        },
        priceline: function () {
            if (this.price.gross === "0.00") {
                if (this.mandatory_priced_addons && !this.original_price) {
                    return "\xA0"; // nbsp, because an empty string would cause the HTML element to collapse
                }
                return strings.free;
            } else {
                return '<span class="pretix-widget-pricebox-currency">' + this.$root.currency + "</span> " + this.display_price;
            }
        },
        taxline: function () {
            if (this.$root.display_net_prices) {
                if (this.price.includes_mixed_tax_rate) {
                    return strings.tax_plus_mixed;
                } else {
                    return django.interpolate(strings.tax_plus, {
                        'rate': autofloatformat(this.price.rate, 2),
                        'taxname': this.price.name
                    }, true);
                }
            } else {
                if (this.price.includes_mixed_tax_rate) {
                    return strings.tax_incl_mixed;
                } else {
                    return django.interpolate(strings.tax_incl, {
                        'rate': autofloatformat(this.price.rate, 2),
                        'taxname': this.price.name
                    }, true);
                }
            }
        }
    }
});
Vue.component('variation', {
    template: ('<div class="pretix-widget-variation" :data-id="variation.id" role="group" v-bind:aria-labelledby="aria_labelledby" v-bind:aria-describedby="variation_desc_id">'
        + '<div class="pretix-widget-item-row">'

        // Variation description
        + '<div class="pretix-widget-item-info-col">'
        + '<div class="pretix-widget-item-title-and-description">'
        + '<strong :id="variation_label_id" class="pretix-widget-item-title" role="heading" v-bind:aria-level="headingLevel">{{ variation.value }}</strong>'
        + '<div :id="variation_desc_id" class="pretix-widget-item-description" v-if="variation.description" v-html="variation.description"></div>'
        + '<p class="pretix-widget-item-meta" '
        + '   v-if="!variation.has_variations && variation.avail[1] !== null && variation.avail[0] === 100">'
        + '<small>{{ quota_left_str }}</small>'
        + '</p>'
        + '</div>'
        + '</div>'

        // Price
        + '<div :id="variation_price_id" class="pretix-widget-item-price-col">'
        + '<pricebox :price="variation.price" :free_price="item.free_price" :original_price="orig_price" '
        + '          :mandatory_priced_addons="item.mandatory_priced_addons" :suggested_price="variation.suggested_price"'
        + '          :field_name="\'price_\' + item.id + \'_\' + variation.id" v-if="$root.showPrices" :item_id="item.id">'
        + '</pricebox>'
        + '<span v-if="!$root.showPrices">&nbsp;</span>'
        + '</div>'

        // Availability
        + '<div class="pretix-widget-item-availability-col">'
        + '<availbox :item="item" :variation="variation"></availbox>'
        + '</div>'

        + '<div class="pretix-widget-clear"></div>'
        + '</div>'
        + '</div>'),
    props: {
        variation: Object,
        item: Object,
        category: Object,
    },
    computed: {
        orig_price: function () {
            if (this.variation.original_price) {
                return this.variation.original_price;
            }
            return this.item.original_price;
        },
        quota_left_str: function () {
            return django.interpolate(strings["quota_left"], [this.variation.avail[1]]);
        },
        variation_label_id: function () {
            return this.$root.html_id + '-variation-label-' + this.item.id + '-' + this.variation.id;
        },
        variation_desc_id: function () {
            return this.$root.html_id + '-variation-desc-' + this.item.id + '-' + this.variation.id;
        },
        variation_price_id: function () {
            return this.$root.html_id + '-variation-price-' + this.item.id + '-' + this.variation.id;
        },
        aria_labelledby: function () {
            return [this.variation_label_id, this.variation_price_id].join(" ");
        },
        headingLevel: function () {
            return this.category.name ? '5' : '4';
        },
    }
});
Vue.component('item', {
    template: ('<div v-bind:class="classObject" :data-id="item.id" role="group" v-bind:aria-labelledby="aria_labelledby" v-bind:aria-describedby="item_desc_id">'
        + '<div class="pretix-widget-item-row pretix-widget-main-item-row">'

        // Product description
        + '<div class="pretix-widget-item-info-col">'
        + '<a :href="item.picture_fullsize" v-if="item.picture" class="pretix-widget-item-picture-link" @click.prevent.stop="lightbox"><img :src="item.picture" class="pretix-widget-item-picture" :alt="picture_alt_text"></a>'
        + '<div class="pretix-widget-item-title-and-description">'
        + '<strong class="pretix-widget-item-title" :id="item_label_id" role="heading" v-bind:aria-level="headingLevel">{{ item.name }}</strong>'
        + '<div class="pretix-widget-item-description" :id="item_desc_id" v-if="item.description" v-html="item.description"></div>'
        + '<p class="pretix-widget-item-meta" v-if="item.order_min && item.order_min > 1">'
        + '<small>{{ min_order_str }}</small>'
        + '</p>'
        + '<p class="pretix-widget-item-meta" '
        + '    v-if="!item.has_variations && item.avail[1] !== null && item.avail[0] === 100">'
        + '<small>{{ quota_left_str }}</small>'
        + '</p>'
        + '</div>'
        + '</div>'

        // Price
        + '<div :id="item_price_id" class="pretix-widget-item-price-col">'
        + '<pricebox :price="item.price" :free_price="item.free_price" v-if="!item.has_variations && $root.showPrices"'
        + '          :mandatory_priced_addons="item.mandatory_priced_addons" :suggested_price="item.suggested_price"'
        + '          :field_name="\'price_\' + item.id" :original_price="item.original_price">'
        + '</pricebox>'
        + '<div class="pretix-widget-pricebox" v-if="item.has_variations && $root.showPrices" v-html="pricerange"></div>'
        + '<span v-if="!$root.showPrices">&nbsp;</span>'
        + '</div>'

        // Availability
        + '<div class="pretix-widget-item-availability-col">'
        + '<button type="button" class="pretix-widget-collapse-indicator" v-if="show_toggle" @click.prevent.stop="expand"'
        + '   v-bind:aria-expanded="expanded ? \'true\': \'false\'" v-bind:aria-controls="item.id + \'-variants\'" v-bind:aria-describedby="item_desc_id">{{ variationsToggleLabel }}</button>'
        + '<availbox v-if="!item.has_variations" :item="item"></availbox>'
        + '</div>'

        + '<div class="pretix-widget-clear"></div>'
        + '</div>'

        // Variations
        + '<div :class="varClasses" v-if="item.has_variations" :id="item.id + \'-variants\'" ref="variations">'
        + '<variation v-for="variation in item.variations" :variation="variation" :item="item" :category="category" :key="variation.id">'
        + '</variation>'
        + '</div>'

        + '</div>'),
    props: {
        item: Object,
        category: Object,
    },
    data: function () {
        return {
            expanded: this.$root.show_variations_expanded
        };
    },
    mounted: function () {
        if (this.$refs.variations) {
            if (!this.expanded) {
                var $this = this;
                this.$refs.variations.hidden = true;
                this.$refs.variations.addEventListener('transitionend', function (event) {
                    if (event.target == this) {
                        this.hidden = !$this.expanded;
                        this.style.maxHeight = 'none';
                    }
                });
                this.$watch('expanded', function (newValue) {
                    var v = this.$refs.variations;
                    v.hidden = false;
                    v.style.maxHeight = (newValue ? 0 : v.scrollHeight) + 'px';
                    // Vue.nextTick does not work here
                    window.setTimeout(function () {
                        v.style.maxHeight = (!newValue ? 0 : v.scrollHeight) + 'px';
                    }, 50);
                })
            }
        }
    },
    methods: {
        expand: function () {
            this.expanded = !this.expanded;
        },
        lightbox: function () {
            this.$root.overlay.lightbox = {
                image: this.item.picture_fullsize,
                description: this.item.name,
            }
        },
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
        picture_alt_text: function () {
            return django.interpolate(strings["image_of"], [this.item.name]);
        },
        headingLevel: function () {
            return this.category.name ? '4' : '3';
        },
        item_label_id: function () {
            return this.$root.html_id + '-item-label-' + this.item.id;
        },
        item_desc_id: function () {
            return this.$root.html_id + '-item-desc-' + this.item.id;
        },
        item_price_id: function () {
            return this.$root.html_id + '-item-price-' + this.item.id;
        },
        aria_labelledby: function () {
            return [this.item_label_id, this.item_price_id].join(" ");
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
            if (this.item.free_price) {
                return django.interpolate(strings.price_from, {
                    'currency': this.$root.currency,
                    'price': floatformat(this.item.min_price, 2)
                }, true).replace(this.$root.currency, '<span class="pretix-widget-pricebox-currency">' + this.$root.currency + '</span>');
            } else if (this.item.min_price !== this.item.max_price) {
                return '<span class="pretix-widget-pricebox-currency">' + this.$root.currency + "</span> " 
                    + floatformat(this.item.min_price, 2) + " – "
                    + floatformat(this.item.max_price, 2);
            } else if (this.item.min_price === "0.00" && this.item.max_price === "0.00") {
                if (this.item.mandatory_priced_addons) {
                    return "\xA0"; // nbsp, because an empty string would cause the HTML element to collapse
                }
                return strings.free;
            } else {
                return '<span class="pretix-widget-pricebox-currency">' + this.$root.currency + "</span> " + floatformat(this.item.min_price, 2);
            }
        },
        variationsToggleLabel: function () {
            return this.expanded ? strings.hide_variations : strings.variations;
        },
    }
});
Vue.component('category', {
    template: ('<div class="pretix-widget-category" :data-id="category.id">'
        + '<h3 class="pretix-widget-category-name" v-if="category.name">{{ category.name }}</h3>'
        + '<div class="pretix-widget-category-description" v-if="category.description" v-html="category.description">'
        + '</div>'
        + '<div class="pretix-widget-category-items">'
        + '<item v-for="item in category.items" :category="category" :item="item" :key="item.id"></item>'
        + '</div>'
        + '</div>'),
    props: {
        category: Object
    }
});

var shared_methods = {
    buy: function (event) {
        if (this.$root.useIframe) {
            if (event) {
                event.preventDefault();
            }
        } else {
            return;
        }
        if (this.$root.is_button && this.$root.items.length === 0) {
            if (this.$root.voucher_code) {
                this.voucher_open(this.$root.voucher_code);
            } else {
                this.resume();
            }
        } else {
            var url = this.$root.formAction + "&locale=" + lang + "&ajax=1";
            this.$root.overlay.frame_loading = true;

            this.async_task_interval = 100;
            var form = this.$refs.form;
            if (form === undefined) {
                form = this.$refs.formcomp.$refs.form;
            }
            api._postFormJSON(url, form, this.buy_callback, this.buy_error_callback);
        }
    },
    buy_error_callback: function (xhr, data) {
        if (xhr.status === 429 && typeof xhr.responseURL !== "undefined") {
            this.$root.overlay.error_message = strings['cart_error_429'];
            this.$root.overlay.frame_loading = false;
            this.$root.overlay.error_url_after = this.$root.newTabTarget;
            this.$root.overlay.error_url_after_new_tab = true;
            return;
        }
        if (xhr.status === 405 && typeof xhr.responseURL !== "undefined") {
            // Likely a redirect!
            this.$root.target_url = xhr.responseURL.substr(0, xhr.responseURL.indexOf("/cart/add") - 18);
            this.$root.overlay.frame_loading = false;
            this.buy();
            return;
        }
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
            if (data.cart_id) {
                this.$root.cart_id = data.cart_id;
                setCookie(this.$root.cookieName, data.cart_id, 30);
            }
            if (data.redirect.substr(0, 1) === '/') {
                data.redirect = this.$root.target_url.replace(/^([^\/]+:\/\/[^\/]+)\/.*$/, "$1") + data.redirect;
            }
            var url = data.redirect;
            if (url.indexOf('?')) {
                url = url + '&iframe=1&locale=' + lang + '&take_cart_id=' + this.$root.cart_id;
            } else {
                url = url + '?iframe=1&locale=' + lang + '&take_cart_id=' + this.$root.cart_id;
            }
            url += this.$root.consent_parameter;
            if (this.$root.additionalURLParams) {
                url += '&' + this.$root.additionalURLParams;
            }
            if (data.success === false) {
                url = url.replace(/checkout\/start/g, "");
                this.$root.overlay.error_message = data.message;
                if (data.has_cart) {
                    this.$root.overlay.error_url_after = url;
                }
                this.$root.overlay.frame_loading = false;
            } else {
                this.$root.overlay.frame_src = url;
            }
        } else {
            this.async_task_id = data.async_id;
            if (data.check_url) {
                this.async_task_check_url = this.$root.target_url.replace(/^([^\/]+:\/\/[^\/]+)\/.*$/, "$1") + data.check_url;
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
            this.voucher_open(this.voucher);
        }
    },
    voucher_open: function (voucher) {
        var redirect_url = this.$root.voucherFormTarget + '&voucher=' + encodeURIComponent(voucher);
        if (this.$root.useIframe) {
            this.$root.overlay.frame_src = redirect_url;
        } else {
            window.open(redirect_url);
        }
    },
    resume: function () {
        var redirect_url;
        redirect_url = this.$root.target_url + 'w/' + widget_id + '/';
        if (this.$root.subevent && !this.$root.cart_id) {
            // button with subevent but no items
            redirect_url += this.$root.subevent + '/';
        }
        redirect_url += '?iframe=1&locale=' + lang;
        if (this.$root.cart_id) {
            redirect_url += '&take_cart_id=' + this.$root.cart_id;
        }
        if (this.$root.widget_data) {
            redirect_url += '&widget_data=' + encodeURIComponent(this.$root.widget_data_json);
        }
        redirect_url += this.$root.consent_parameter;
        if (this.$root.additionalURLParams) {
            redirect_url += '&' + this.$root.additionalURLParams;
        }
        if (this.$root.useIframe) {
            this.$root.overlay.frame_src = redirect_url;
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
        mobile: false,
    }
};

var shared_loading_fragment = (
    '<div class="pretix-widget-loading" v-show="$root.loading > 0">'
    + '<svg width="128" height="128" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path class="pretix-widget-primary-color" d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
    + '</div>'
);

var shared_iframe_fragment = (
    '<dialog :class="frameClasses" aria-label="'+strings.checkout+'" @close="close" @cancel="cancel">'
    + '<div class="pretix-widget-frame-loading" v-show="$root.frame_loading">'
        + '<svg width="256" height="256" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path class="pretix-widget-primary-color" d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
        + '<p :class="cancelBlockedClasses"><strong>'+strings.cancel_blocked+'</strong></p>'
    + '</div>'
    + '<div class="pretix-widget-frame-inner" ref="frame-container" v-show="$root.frame_shown">'
        + '<form class="pretix-widget-frame-close" method="dialog"><button aria-label="'+strings.close_checkout+'" autofocus="autofocus">'
            + '<svg alt="'+strings.close+'" height="16" viewBox="0 0 512 512" width="16" xmlns="http://www.w3.org/2000/svg"><path fill="#fff" d="M437.5,386.6L306.9,256l130.6-130.6c14.1-14.1,14.1-36.8,0-50.9c-14.1-14.1-36.8-14.1-50.9,0L256,205.1L125.4,74.5  c-14.1-14.1-36.8-14.1-50.9,0c-14.1,14.1-14.1,36.8,0,50.9L205.1,256L74.5,386.6c-14.1,14.1-14.1,36.8,0,50.9  c14.1,14.1,36.8,14.1,50.9,0L256,306.9l130.6,130.6c14.1,14.1,36.8,14.1,50.9,0C451.5,423.4,451.5,400.6,437.5,386.6z"/></svg>'
        + '</button></form>'
        + '<iframe frameborder="0" width="650" height="650" @load="iframeLoaded" '
        + '        :name="$root.parent.widget_id" src="about:blank" v-once'
        + '        allow="autoplay *; camera *; fullscreen *; payment *"'
        + '        title="'+strings.checkout+'"'
        + '        referrerpolicy="origin">'
        + 'Please enable frames in your browser!'
        + '</iframe>'
    + '</div>'
    + '</dialog>'
);

var shared_alert_fragment = (
    '<dialog :class="alertClasses" role="alertdialog" v-bind:aria-labelledby="$root.parent.html_id + \'-error-message\'" @close="errorClose">'
    + '<form class="pretix-widget-alert-box" method="dialog">'
    + '<p :id="$root.parent.html_id + \'-error-message\'">{{ $root.error_message }}</p>'
    + '<p><button v-if="$root.error_url_after" value="continue" autofocus v-bind:aria-describedby="$root.parent.html_id + \'-error-message\'">' + strings.continue + '</button>'
    + '<button v-else autofocus v-bind:aria-describedby="$root.parent.html_id + \'-error-message\'">' + strings.close + '</button></p>'
    + '</form>'
    + '<transition name="bounce">'
    + '<svg v-if="$root.error_message" width="64" height="64" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg" class="pretix-widget-alert-icon"><path style="fill:#ffffff;" d="M 599.86438,303.72882 H 1203.5254 V 1503.4576 H 599.86438 Z" /><path class="pretix-widget-primary-color" d="M896 128q209 0 385.5 103t279.5 279.5 103 385.5-103 385.5-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103zm128 1247v-190q0-14-9-23.5t-22-9.5h-192q-13 0-23 10t-10 23v190q0 13 10 23t23 10h192q13 0 22-9.5t9-23.5zm-2-344l18-621q0-12-10-18-10-8-24-8h-220q-14 0-24 8-10 6-10 18l17 621q0 10 10 17.5t24 7.5h185q14 0 23.5-7.5t10.5-17.5z"/></svg>'
    + '</transition>'
    + '</dialog>'
);

var shared_lightbox_fragment = (
    '<dialog :class="lightboxClasses" role="alertdialog" @close="lightboxClose">'
        + '<div class="pretix-widget-lightbox-loading" v-if="$root.lightbox?.loading">'
            + '<svg width="256" height="256" viewBox="0 0 1792 1792" xmlns="http://www.w3.org/2000/svg"><path class="pretix-widget-primary-color" d="M1152 896q0-106-75-181t-181-75-181 75-75 181 75 181 181 75 181-75 75-181zm512-109v222q0 12-8 23t-20 13l-185 28q-19 54-39 91 35 50 107 138 10 12 10 25t-9 23q-27 37-99 108t-94 71q-12 0-26-9l-138-108q-44 23-91 38-16 136-29 186-7 28-36 28h-222q-14 0-24.5-8.5t-11.5-21.5l-28-184q-49-16-90-37l-141 107q-10 9-25 9-14 0-25-11-126-114-165-168-7-10-7-23 0-12 8-23 15-21 51-66.5t54-70.5q-27-50-41-99l-183-27q-13-2-21-12.5t-8-23.5v-222q0-12 8-23t19-13l186-28q14-46 39-92-40-57-107-138-10-12-10-24 0-10 9-23 26-36 98.5-107.5t94.5-71.5q13 0 26 10l138 107q44-23 91-38 16-136 29-186 7-28 36-28h222q14 0 24.5 8.5t11.5 21.5l28 184q49 16 90 37l142-107q9-9 24-9 13 0 25 10 129 119 165 170 7 8 7 22 0 12-8 23-15 21-51 66.5t-54 70.5q26 50 41 98l183 28q13 2 21 12.5t8 23.5z"/></svg>'
        + '</div>'
        + '<div class="pretix-widget-lightbox-inner" v-if="$root.lightbox">'
            + '<form class="pretix-widget-lightbox-close" method="dialog"><button aria-label="'+strings.close+'" autofocus="autofocus">'
                + '<svg alt="'+strings.close+'" height="16" viewBox="0 0 512 512" width="16" xmlns="http://www.w3.org/2000/svg"><path fill="#fff" d="M437.5,386.6L306.9,256l130.6-130.6c14.1-14.1,14.1-36.8,0-50.9c-14.1-14.1-36.8-14.1-50.9,0L256,205.1L125.4,74.5  c-14.1-14.1-36.8-14.1-50.9,0c-14.1,14.1-14.1,36.8,0,50.9L205.1,256L74.5,386.6c-14.1,14.1-14.1,36.8,0,50.9  c14.1,14.1,36.8,14.1,50.9,0L256,306.9l130.6,130.6c14.1,14.1,36.8,14.1,50.9,0C451.5,423.4,451.5,400.6,437.5,386.6z"/></svg>'
            + '</button></form>'
            + '<figure class="pretix-widget-lightbox-image">'
                + '<img :src="$root.lightbox.image" :alt="$root.lightbox.description" @load="lightboxLoaded" ref="lightboxImage" crossorigin>'
                + '<figcaption v-if="$root.lightbox.description">{{$root.lightbox.description}}</figcaption>'
            + '</figure>'
        + '</div>'
    + '</dialog>'
);

Vue.component('pretix-overlay', {
    template: ('<div class="pretix-widget-overlay">'
        + shared_iframe_fragment
        + shared_alert_fragment
        + shared_lightbox_fragment
        + '</div>'
    ),
    data: function () {
        return {
            cancelBlocked: false,
        }
    },
    watch: {
        '$root.lightbox': function (newValue, oldValue) {
            if (newValue) {
                if (newValue.image != oldValue?.image) {
                    this.$set(newValue, "loading", true);
                }
                if (!oldValue) {
                    this.$el?.querySelector(".pretix-widget-lightbox-holder").showModal();
                }
            }
        },
        '$root.error_message': function (newValue, oldValue) {
            if (newValue) {
                if (!oldValue) {
                    this.$el?.querySelector(".pretix-widget-alert-holder").showModal();
                }
            }
        },
        '$root.frame_shown': function (newValue) {
            if (newValue) {
                var btn = this.$el?.querySelector('.pretix-widget-frame-close button');
                this.$nextTick(function() {
                    btn.focus();
                });
            }
        },
    },
    computed: {
        frameClasses: function () {
            return {
                'pretix-widget-frame-holder': true,
                'pretix-widget-frame-shown': this.$root.frame_shown || this.$root.frame_loading,
                'pretix-widget-frame-isloading': this.$root.frame_loading,
            };
        },
        alertClasses: function () {
            return {
                'pretix-widget-alert-holder': true,
                'pretix-widget-alert-shown': this.$root.error_message,
            };
        },
        lightboxClasses: function () {
            return {
                'pretix-widget-lightbox-holder': true,
                'pretix-widget-lightbox-shown': this.$root.lightbox,
                'pretix-widget-lightbox-isloading': this.$root.lightbox?.loading,
            };
        },
        cancelBlockedClasses: function () {
            return {
                'pretix-widget-visibility-hidden': !this.cancelBlocked,
            }  
        },
    },
    mounted () {
        window.addEventListener('message', this.onMessage, false);
    },
    unmounted () {
        window.removeEventListener('message', this.onMessage, false);
    },
    methods: {
        onMessage: function(e) {
            if (e.data.type && e.data.type == "pretix:widget:title") {
                this.$el.querySelector("iframe").title = e.data.title;
            }
        },
        lightboxClose: function () {
            this.$root.lightbox = null;
        },
        lightboxLoaded: function () {
            this.$root.lightbox.loading = false;
        },
        errorClose: function (e) {
            var dialog = e.target;
            if (dialog.returnValue == "continue" && this.$root.error_url_after) {
                if (this.$root.error_url_after_new_tab) {
                    window.open(this.$root.error_url_after);
                } else if (this.$root.overlay) {
                    this.$root.overlay.frame_src = this.$root.error_url_after;
                    this.$root.frame_loading = true;
                }
            }
            this.$root.error_message = null;
            this.$root.error_url_after = null;
            this.$root.error_url_after_new_tab = false;
        },
        close: function (e) {
            if (this.$root.frame_loading) {
                // Chrome does not allow blocking dialog.cancel event more than once
                // => wiggle the loading-element and re-open the modal
                this.cancel(e);
                e.target.showModal();
                return;
            }
            this.$root.frame_shown = false;
            this.$root.parent.frame_dismissed = true;
            this.$root.frame_src = "";
            this.$root.parent.reload();
            this.$root.parent.trigger_close_callback();
        },
        cancel: function (e) {
            // do not allow to cancel while frame is loading as we cannot abort the operation
            if (this.$root.frame_loading) {
                e.preventDefault();
                e.target.addEventListener("animationend", function () {
                    e.target.classList.remove("pretix-widget-shake-once");
                }, {once: true});
                e.target.classList.add("pretix-widget-shake-once");
                this.cancelBlocked = true;
            }
        },
        iframeLoaded: function () {
            if (this.$root.frame_loading) {
                this.$root.frame_loading = false;
                this.cancelBlocked = false;
                if (this.$root.frame_src) {
                    this.$root.frame_shown = true;
                }
            }
        },
    }
});

Vue.component('pretix-widget-event-form', {
    template: ('<div class="pretix-widget-event-form">'
        // Back navigation
        + '<div class="pretix-widget-event-list-back" v-if="$root.events || $root.weeks || $root.days">'
        + '<a href="#" rel="back" @click.prevent.stop="back_to_list" v-if="!$root.subevent">&lsaquo; '
        + strings['back_to_list']
        + '</a>'
        + '<a href="#" rel="back" @click.prevent.stop="back_to_list" v-if="$root.subevent">&lsaquo; '
        + strings['back_to_dates']
        + '</a>'
        + '</div>'

        // Event name
        + '<div class="pretix-widget-event-header" v-if="display_event_info">'
        + '<strong role="heading" aria-level="2">{{ $root.name }}</strong>'
        + '</div>'

        // Date range
        + '<div class="pretix-widget-event-details" v-if="display_event_info && $root.date_range">'
        + '{{ $root.date_range }}'
        + '</div>'

        // Location
        + '<div class="pretix-widget-event-location" v-if="display_event_info && $root.location" v-html="$root.location"></div>'

        // Form start
        + '<div class="pretix-widget-event-description" v-if="display_event_info && $root.frontpage_text" v-html="$root.frontpage_text"></div>'
        + '<form method="post" :action="$root.formAction" ref="form" :target="$root.formTarget" @submit="$parent.buy">'
        + '<input type="hidden" name="_voucher_code" :value="$root.voucher_code" v-if="$root.voucher_code">'
        + '<input type="hidden" name="subevent" :value="$root.subevent" />'
        + '<input type="hidden" name="widget_data" :value="$root.widget_data_json" />'
        + '<input v-if="$root.consent_parameter_value" type="hidden" name="consent" :value="$root.consent_parameter_value" />'

        // Error message
        + '<div class="pretix-widget-error-message" v-if="$root.error">{{ $root.error }}</div>'

        // Resume cart
        + '<div class="pretix-widget-info-message pretix-widget-clickable" v-if="$root.cart_exists">'
        + '<span :id="id_cart_exists_msg">' + strings['cart_exists'] + '</span>'
        + '<button @click.prevent.stop="$parent.resume" class="pretix-widget-resume-button" type="button" v-bind:aria-describedby="id_cart_exists_msg">'
        + strings['resume_checkout']
        + '</button>'
        + '</div>'

        // Seating plan
        + '<div class="pretix-widget-seating-link-wrapper" v-if="this.$root.has_seating_plan">'
        + '<button class="pretix-widget-seating-link" type="button" @click.prevent.stop="$root.startseating">'
        + strings['show_seating']
        + '</button>'
        + '</div>'

        // Waiting list for seating plan
        + '<div class="pretix-widget-seating-waitinglist" v-if="this.$root.has_seating_plan && this.$root.has_seating_plan_waitinglist">'
        + '<div class="pretix-widget-seating-waitinglist-text">'
        + strings['seating_plan_waiting_list']
        + '</div>'
        + '<div class="pretix-widget-seating-waitinglist-button-wrap">'
        + '<button class="pretix-widget-seating-waitinglist-button" @click.prevent.stop="$root.startwaiting">'
        + strings['waiting_list']
        + '</button>'
        + '</div>'
        + '<div class="pretix-widget-clear"></div>'
        + '</div>'

        // Actual product list
        + '<category v-for="category in this.$root.categories" :category="category" :key="category.id"></category>'

        // Buy button
        + '<div class="pretix-widget-action" v-if="$root.display_add_to_cart">'
        + '<button v-if="!this.$root.cart_exists || this.is_items_selected" type="submit" v-bind:aria-describedby="id_cart_exists_msg">{{ buy_label }}</button>'
        + '<button v-else @click.prevent.stop="$parent.resume" type="button" v-bind:aria-describedby="id_cart_exists_msg">'
        + strings['resume_checkout']
        + '</button>'
        + '</div>'

        + '</form>'

        // Voucher form
        + '<form method="get" :action="$root.voucherFormTarget" target="_blank" '
        + '      v-if="$root.vouchers_exist && !$root.disable_vouchers && !$root.voucher_code">'
        + '<div class="pretix-widget-voucher">'
        + '<h3 class="pretix-widget-voucher-headline" :id="aria_labelledby">'+ strings['redeem_voucher'] +'</h3>'
        + '<div v-if="$root.voucher_explanation_text" class="pretix-widget-voucher-text" v-html="$root.voucher_explanation_text"></div>'
        + '<div class="pretix-widget-voucher-input-wrap">'
        + '<input :id="id_voucher_input" class="pretix-widget-voucher-input" ref="voucherinput" type="text" v-model="$parent.voucher" name="voucher" placeholder="'+strings.voucher_code+'" v-bind:aria-labelledby="aria_labelledby">'
        + '</div>'
        + '<input type="hidden" v-for="p in hiddenParams" :name="p[0]" :value="p[1]" />'
        + '<div class="pretix-widget-voucher-button-wrap">'
        + '<button @click="$parent.redeem">' + strings.redeem + '</button>'
        + '</div>'
        + '<div class="pretix-widget-clear"></div>'
        + '</div>'
        + '</form>'

        + '</div>'
    ),
    data: function () {
        return {
            is_items_selected: false,
        }
    },
    watch: {
        '$root.overlay.frame_shown': function (newValue) {
            if (!newValue) {
                this.$refs.form.reset();
                this.calc_items_selected();
            }
        }
    },
    mounted: function() {
        this.$root.$on('focus_voucher_field', this.focus_voucher_field);
        this.$refs.form.addEventListener("change", this.calc_items_selected);
    },
    beforeDestroy: function() {
        this.$root.$off('focus_voucher_field', this.focus_voucher_field);
        this.$refs.form.removeEventListener("change", this.calc_items_selected);
    },
    computed: {
        id_voucher_input: function () {
            return this.$root.html_id + '-voucher-input';
        },
        aria_labelledby: function () {
            return this.$root.html_id + '-voucher-headline';
        },
        display_event_info: function () {
            return this.$root.display_event_info || (this.$root.display_event_info === null && (this.$root.events || this.$root.weeks || this.$root.days));
        },
        id_cart_exists_msg: function () {
            return this.$root.html_id + '-cart-exists';
        },
        buy_label: function () {
            var i, j, k, all_free = true;
            for (i = 0; i < this.$root.categories.length; i++) {
                var cat = this.$root.categories[i];
                for (j = 0; j < cat.items.length; j++) {
                    var item = cat.items[j];
                    for (k = 0; k < item.variations.length; k++) {
                        var v = item.variations[k];
                        if (v.price.gross !== "0.00") {
                            all_free = false;
                            break;
                        }
                    }
                    if ((item.variations.length === 0 && item.price.gross !== "0.00") || item.mandatory_priced_addons) {
                        all_free = false;
                        break;
                    }
                }
                if (!all_free) {
                    break;
                }
            }
            if (all_free) {
                return strings.register;
            } else {
                return strings.buy;
            }
        },
        hiddenParams: function () {
            var params = new URL(this.$root.voucherFormTarget).searchParams;
            params.delete("iframe");
            params.delete("take_cart_id");
            return [...params.entries()];
        },
    },
    methods: {
        back_to_list: function() {
            this.$root.target_url = this.$root.parent_stack.pop();
            this.$root.error = null;
            if (!this.$root.subevent) {
                // reset if we are not in a series
                this.$root.name = null;
                this.$root.frontpage_text = null;
            }
            this.$root.subevent = null;
            this.$root.offset = 0;
            this.$root.append_events = false;
            this.$root.trigger_load_callback();
            if (this.$root.events !== undefined && this.$root.events !== null) {
                this.$root.view = "events";
            } else if (this.$root.days !== undefined && this.$root.days !== null) {
                this.$root.view = "days";
            } else {
                this.$root.view = "weeks";
            }

            var $el = this.$root.$el;
            this.$root.$nextTick(function() {
                // wait for redraw, then focus content element for better a11y
                $el.focus();
            });
        },
        calc_items_selected: function () {
            this.is_items_selected = [...this.$refs.form.querySelectorAll("input[type=checkbox], input[type=radio]")].some(function(element) {
                return element.checked;
            }) || [...this.$refs.form.querySelectorAll(".pretix-widget-item-count-group input")].some(function(element) {
                return parseInt(element.value || "0") > 0;
            });
        },
    }
});

Vue.component('pretix-widget-event-list-filter-field', {
    template: ('<div class="pretix-widget-event-list-filter-field">'
        + '<label :for="id">{{ field.label }}</label>'
        + '<select :id="id" :name="field.key" :value="currentValue">'
        + '<option v-for="choice in field.choices" :value="choice[0]">{{ choice[1] }}</option>'
        + '</select>'
        + '</div>'),
    props: {
        field: Object
    },
    computed: {
        id: function () {
            return widget_id + "_" + this.field.key;
        },
        currentValue: function () {
            var filterParams = new URLSearchParams(this.$root.filter);
            return filterParams.get(this.field.key) || "";
        },
    },
});

Vue.component('pretix-widget-event-list-filter-form', {
    template: ('<form ref="filterform" class="pretix-widget-event-list-filter-form" @submit="onSubmit">'
            + '<fieldset class="pretix-widget-event-list-filter-fieldset">'
                + '<legend>' + strings.filter_events_by + '</legend>'
                + '<pretix-widget-event-list-filter-field v-for="field in $root.meta_filter_fields" :field="field" :key="field.key"></pretix-widget-event-list-filter-field>'
                + '<button>' + strings.filter + '</button>'
            + '</fieldset>'
        + '</form>'),
    methods: {
        onSubmit: function(e) {
            e.preventDefault();
            var formData = new FormData(this.$refs.filterform);
            var filterParams = new URLSearchParams(formData);
            formData.forEach(function (value, key) {
                if (value == "") {
                    filterParams.delete(key);
                }
            });

            this.$root.filter = filterParams.toString();
            this.$root.loading++;
            this.$root.reload();
        },
    },
});

Vue.component('pretix-widget-event-list-entry', {
    template: ('<a href="#" :class="classObject" @click.prevent.stop="select">'
        + '<div class="pretix-widget-event-list-entry-name">{{ event.name }}</div>'
        + '<div class="pretix-widget-event-list-entry-date">{{ event.date_range }}</div>'
        + '<div class="pretix-widget-event-list-entry-location">{{ location }}</div>'  // hidden by css for now, but
                                                                                       // used by a few people
        + '<div class="pretix-widget-event-list-entry-availability"><span>{{ event.availability.text }}</span></div>'
        + '</a>'),
    props: {
        event: Object
    },
    computed: {
        classObject: function () {
            var o = {
                'pretix-widget-event-list-entry': true
            };
            o['pretix-widget-event-availability-' + this.event.availability.color] = true;
            if (this.event.availability.reason) {
                o['pretix-widget-event-availability-' + this.event.availability.reason] = true;
            }
            return o;
        },
        location: function () {
            return this.event.location.replace(/\s*\n\s*/g, ', ');
        }
    },
    methods: {
        select: function () {
            this.$root.parent_stack.push(this.$root.target_url);
            this.$root.target_url = this.event.event_url;
            this.$root.error = null;
            this.$root.subevent = this.event.subevent;
            this.$root.loading++;
            this.$root.reload();
        }
    }
});

Vue.component('pretix-widget-event-list', {
    template: ('<div class="pretix-widget-event-list">'
        + '<div class="pretix-widget-back" v-if="$root.weeks || $root.parent_stack.length > 0">'
        + '<a href="#" rel="prev" @click.prevent.stop="back_to_calendar">&lsaquo; '
        + strings['back']
        + '</a>'
        + '</div>'
        + '<div class="pretix-widget-event-header" v-if="display_event_info">'
        + '<strong>{{ $root.name }}</strong>'
        + '</div>'
        + '<div class="pretix-widget-event-description" v-if="display_event_info && $root.frontpage_text" v-html="$root.frontpage_text"></div>'
        + '<pretix-widget-event-list-filter-form v-if="!$root.disable_filters && $root.meta_filter_fields.length > 0"></pretix-widget-event-list-filter-form>'
        + '<pretix-widget-event-list-entry v-for="event in $root.events" :event="event" :key="event.url"></pretix-widget-event-list-entry>'
        + '<p class="pretix-widget-event-list-load-more" v-if="$root.has_more_events"><button @click.prevent.stop="load_more">'+strings.load_more+'</button></p>'
        + '</div>'),
    computed: {
        display_event_info: function () {
            return this.$root.display_event_info || (this.$root.display_event_info === null && this.$root.parent_stack.length > 0);
        },
    },
    methods: {
        back_to_calendar: function () {
            // make sure to always focus content element
            this.$nextTick(function () {
                this.$root.$el.focus();
            });
            this.$root.offset = 0;
            this.$root.append_events = false;
            if (this.$root.weeks) {
                this.$root.events = undefined;
                this.$root.view = "weeks";
                this.$root.name = null;
                this.$root.frontpage_text = null;
            } else {
                this.$root.loading++;
                this.$root.target_url = this.$root.parent_stack.pop();
                this.$root.error = null;
                this.$root.reload();
            }
        },
        load_more: function () {
            this.$root.append_events = true;
            this.$root.offset += 50;
            this.$root.loading++;
            this.$root.reload();
        }
    }
});

Vue.component('pretix-widget-event-calendar-event', {
    template: ('<a href="#" :class="classObject" @click.prevent.stop="select" v-bind:aria-describedby="describedby">'
        + '<strong class="pretix-widget-event-calendar-event-name">'
        + '{{ event.name }}'
        + '</strong>'
        + '<div class="pretix-widget-event-calendar-event-date" v-if="!event.continued && event.time">{{ event.time }}</div>'
        + '<div class="pretix-widget-event-calendar-event-availability" v-if="!event.continued && event.availability.text">{{ event.availability.text }}</div>'
        + '</a>'),
    props: {
        event: Object,
        describedby: String,
    },
    computed: {
        classObject: function () {
            var o = {
                'pretix-widget-event-calendar-event': true
            };
            o['pretix-widget-event-availability-' + this.event.availability.color] = true;
            if (this.event.availability.reason) {
                o['pretix-widget-event-availability-' + this.event.availability.reason] = true;
            }
            return o
        }
    },
    methods: {
        select: function () {
            this.$root.parent_stack.push(this.$root.target_url);
            this.$root.target_url = this.event.event_url;
            this.$root.error = null;
            this.$root.subevent = this.event.subevent;
            this.$root.loading++;
            this.$root.reload();
        }
    }
});

Vue.component('pretix-widget-event-week-cell', {
    template: ('<div :class="classObject" @click.prevent.stop="selectDay">'
        + '<div class="pretix-widget-event-calendar-day" v-if="day" :id="id">'
        + '{{ dayhead }}'
        + '</div>'
        + '<div class="pretix-widget-event-calendar-events" v-if="day">'
        + '<pretix-widget-event-calendar-event v-for="e in day.events" :event="e" :describedby="id"></pretix-widget-event-calendar-event>'
        + '</div>'
        + '</div>'),
    props: {
        day: Object,
    },
    methods: {
        selectDay: function () {
            if (!this.day || !this.day.events.length || !this.$parent.$parent.$parent.mobile) {
                return;
            }
            if (this.day.events.length === 1) {
                var ev = this.day.events[0];
                this.$root.parent_stack.push(this.$root.target_url);
                this.$root.target_url = ev.event_url;
                this.$root.error = null;
                this.$root.subevent = ev.subevent;
                this.$root.loading++;
                this.$root.reload();
            } else {
                this.$root.events = this.day.events;
                this.$root.view = "events";
            }
        }
    },
    computed: {
        id: function () {
            return this.day ? this.$root.html_id + '-' + this.day.date : '';
        },
        dayhead: function () {
            if (!this.day) {
                return;
            }
            return this.day.day_formatted;
        },
        classObject: function () {
            var o = {};
            if (this.day && this.day.events.length > 0) {
                o['pretix-widget-has-events'] = true;
                var best = 'red';
                var all_low = true;
                for (var i = 0; i < this.day.events.length; i++) {
                    var ev = this.day.events[i];
                    if (ev.availability.color === 'green') {
                        best = 'green';
                        if (ev.availability.reason !== 'low') {
                            all_low = false;
                        }
                    } else if (ev.availability.color === 'orange' && best !== 'green') {
                        best = 'orange'
                    }
                }
                o['pretix-widget-day-availability-' + best] = true;
                if (best === 'green' && all_low) {
                    o['pretix-widget-day-availability-low'] = true;
                }
            }
            return o
        }
    }
});

Vue.component('pretix-widget-event-calendar-cell', {
    template: ('<td :class="classObject" :role="role" :tabindex="tabindex" v-bind:aria-label="date">'
        + '<div class="pretix-widget-event-calendar-day" v-if="day" v-bind:aria-label="date">'
        + '{{ daynum }}'
        + '</div>'
        + '<div class="pretix-widget-event-calendar-events" v-if="day">'
        + '<pretix-widget-event-calendar-event v-for="e in day.events" :event="e"></pretix-widget-event-calendar-event>'
        + '</div>'
        + '</td>'),
    props: {
        day: Object,
    },
    methods: {
        selectDay: function (e) {
            if (!this.day || !this.day.events.length || !this.$parent.$parent.$parent.mobile) {
                return;
            }
            e.preventDefault();
            e.stopPropagation();
            if (this.day.events.length === 1) {
                var ev = this.day.events[0];
                this.$root.parent_stack.push(this.$root.target_url);
                this.$root.target_url = ev.event_url;
                this.$root.error = null;
                this.$root.subevent = ev.subevent;
                this.$root.loading++;
                this.$root.reload();
            } else {
                this.$root.events = this.day.events;
                this.$root.view = "events";
            }
        },
        onKeyDown: function (e) {
            var keyDown = e.key !== undefined ? e.key : e.keyCode;
            if ( (keyDown === 'Enter' || keyDown === 13) || (['Spacebar', ' '].indexOf(keyDown) >= 0 || keyDown === 32)) {
                // (prevent default so the page doesn't scroll when pressing space)
                e.preventDefault();
                this.selectDay(e);
            }
        },
    },
    mounted: function () {
        if (this.role == 'button') {
            this.$el.addEventListener("click", this.selectDay);
            this.$el.addEventListener("keydown", this.onKeyDown);
        }
    },
    watch: {
        role: function (newValue) {
            if (newValue == 'button') {
                this.$el.addEventListener("click", this.selectDay);
                this.$el.addEventListener("keydown", this.onKeyDown);
            } else {
                this.$el.removeEventListener("click", this.selectDay);
                this.$el.removeEventListener("keydown", this.onKeyDown);
            }
        }
    },
    computed: {
        role: function () {
            return (!this.day || !this.day.events.length || !this.$parent.$parent.$parent.mobile) ? 'cell' : 'button';
        },
        tabindex: function () {
            return this.role == 'button' ? '0' : '-1';
        },
        daynum: function () {
            if (!this.day) {
                return;
            }
            return this.day.date.substr(8);
        },
        date: function () {
            return this.day ? (new Date(this.day.date)).toLocaleDateString() : '';
        },
        classObject: function () {
            var o = {};
            if (this.day && this.day.events.length > 0) {
                o['pretix-widget-has-events'] = true;
                var best = 'red';
                var all_low = true;
                for (var i = 0; i < this.day.events.length; i++) {
                    var ev = this.day.events[i];
                    if (ev.availability.color === 'green') {
                        best = 'green';
                        if (ev.availability.reason !== 'low') {
                            all_low = false;
                        }
                    } else if (ev.availability.color === 'orange' && best !== 'green') {
                        best = 'orange'
                    }
                }
                o['pretix-widget-day-availability-' + best] = true;
                if (best === 'green' && all_low) {
                    o['pretix-widget-day-availability-low'] = true;
                }
            }
            return o
        }
    }
});

Vue.component('pretix-widget-event-calendar-row', {
    template: ('<tr>'
        + '<pretix-widget-event-calendar-cell v-for="d in week" :day="d"></pretix-widget-event-calendar-cell>'
        + '</tr>'),
    props: {
        week: Array
    },
});

Vue.component('pretix-widget-event-calendar', {
    template: ('<div class="pretix-widget-event-calendar" ref="calendar">'

        // Back navigation
        + '<div class="pretix-widget-back" v-if="$root.events !== undefined">'
        + '<a href="#" @click.prevent.stop="back_to_list" role="button">&lsaquo; '
        + strings['back']
        + '</a>'
        + '</div>'

        // Headline
        + '<div class="pretix-widget-event-header" v-if="display_event_info">'
        + '<strong>{{ $root.name }}</strong>'
        + '</div>'
        + '<div class="pretix-widget-event-description" v-if="display_event_info && $root.frontpage_text" v-html="$root.frontpage_text"></div>'

        // Filter
        + '<pretix-widget-event-list-filter-form v-if="!$root.disable_filters && $root.meta_filter_fields.length > 0"></pretix-widget-event-list-filter-form>'

        // Calendar navigation
        + '<div class="pretix-widget-event-calendar-head">'
        + '<a class="pretix-widget-event-calendar-previous-month" href="#" @click.prevent.stop="prevmonth">&laquo; '
        + strings['previous_month']
        + '</a> '
        + '<strong :id="aria_labelledby">{{ monthname }}</strong> '
        + '<a class="pretix-widget-event-calendar-next-month" href="#" @click.prevent.stop="nextmonth">'
        + strings['next_month']
        + ' &raquo;</a>'
        + '</div>'

        // Calendar
        + '<table class="pretix-widget-event-calendar-table" :id="id" tabindex="0" v-bind:aria-labelledby="aria_labelledby">'
        + '<thead>'
        + '<tr>'
        + '<th aria-label="' + strings['days']['MONDAY'] + '">' + strings['days']['MO'] + '</th>'
        + '<th aria-label="' + strings['days']['TUESDAY'] + '">' + strings['days']['TU'] + '</th>'
        + '<th aria-label="' + strings['days']['WEDNESDAY'] + '">' + strings['days']['WE'] + '</th>'
        + '<th aria-label="' + strings['days']['THURSDAY'] + '">' + strings['days']['TH'] + '</th>'
        + '<th aria-label="' + strings['days']['FRIDAY'] + '">' + strings['days']['FR'] + '</th>'
        + '<th aria-label="' + strings['days']['SATURDAY'] + '">' + strings['days']['SA'] + '</th>'
        + '<th aria-label="' + strings['days']['SUNDAY'] + '">' + strings['days']['SU'] + '</th>'
        + '</tr>'
        + '</thead>'
        + '<tbody>'
        + '<pretix-widget-event-calendar-row v-for="week in $root.weeks" :week="week"></pretix-widget-event-calendar-row>'
        + '</tbody>'
        + '</table>'
        + '</div>'),
    computed: {
        display_event_info: function () {
            return this.$root.display_event_info || (this.$root.display_event_info === null && this.$root.parent_stack.length > 0);
        },
        monthname: function () {
            return strings['months'][this.$root.date.substr(5, 2)] + ' ' + this.$root.date.substr(0, 4);
        },
        id: function () {
            return this.$root.html_id + "-event-calendar-table";
        },
        aria_labelledby: function () {
            return this.$root.html_id + "-event-calendar-table-label";
        },
    },
    methods: {
        back_to_list: function () {
            this.$root.weeks = undefined;
            this.$root.view = "events";
            this.$root.name = null;
            this.$root.frontpage_text = null;
        },
        prevmonth: function () {
            var curMonth = parseInt(this.$root.date.substr(5, 2));
            var curYear = parseInt(this.$root.date.substr(0, 4));
            curMonth--;
            if (curMonth < 1) {
                curMonth = 12;
                curYear--;
            }
            this.$root.date = String(curYear) + "-" + padNumber(curMonth, 2) + "-01";
            this.$root.loading++;
            this.$root.reload({focus: '#'+this.id});
        },
        nextmonth: function () {
            var curMonth = parseInt(this.$root.date.substr(5, 2));
            var curYear = parseInt(this.$root.date.substr(0, 4));
            curMonth++;
            if (curMonth > 12) {
                curMonth = 1;
                curYear++;
            }
            this.$root.date = String(curYear) + "-" + padNumber(curMonth, 2) + "-01";
            this.$root.loading++;
            this.$root.reload({focus: '#'+this.id});
        }
    },
});

Vue.component('pretix-widget-event-week-calendar', {
    template: ('<div class="pretix-widget-event-calendar pretix-widget-event-week-calendar" ref="weekcalendar">'
        // Back navigation
        + '<div class="pretix-widget-back" v-if="$root.events !== undefined">'
        + '<a href="#" @click.prevent.stop="back_to_list" role="button">&lsaquo; '
        + strings['back']
        + '</a>'
        + '</div>'

        // Event header
        + '<div class="pretix-widget-event-header" v-if="display_event_info">'
        + '<strong>{{ $root.name }}</strong>'
        + '</div>'

        // Filter
        + '<pretix-widget-event-list-filter-form v-if="!$root.disable_filters && $root.meta_filter_fields.length > 0"></pretix-widget-event-list-filter-form>'

        // Calendar navigation
        + '<div class="pretix-widget-event-description" v-if="$root.frontpage_text && display_event_info" v-html="$root.frontpage_text"></div>'
        + '<div class="pretix-widget-event-calendar-head">'
        + '<a class="pretix-widget-event-calendar-previous-month" href="#" @click.prevent.stop="prevweek" role="button">&laquo; '
        + strings['previous_week']
        + '</a> '
        + '<strong>{{ weekname }}</strong> '
        + '<a class="pretix-widget-event-calendar-next-month" href="#" @click.prevent.stop="nextweek" role="button">'
        + strings['next_week']
        + ' &raquo;</a>'
        + '</div>'

        // Actual calendar
        + '<div class="pretix-widget-event-week-table" :id="id" tabindex="0" v-bind:aria-label="weekname">'
        + '<div class="pretix-widget-event-week-col" v-for="d in $root.days">'
        + '<pretix-widget-event-week-cell :day="d">'
        + '</pretix-widget-event-week-cell>'
        + '</div>'
        + '</div>'

        + '</div>'
        + '</div>'),
    computed: {
        display_event_info: function () {
            return this.$root.display_event_info || (this.$root.display_event_info === null && this.$root.parent_stack.length > 0);
        },
        weekname: function () {
            var curWeek = this.$root.week[1];
            var curYear = this.$root.week[0];
            return curWeek + ' / ' + curYear;
        },
        id: function () {
            return this.$root.html_id + "-event-week-table";
        },
    },
    methods: {
        back_to_list: function () {
            this.$root.weeks = undefined;
            this.$root.name = null;
            this.$root.frontpage_text = null;
            this.$root.view = "events";
        },
        prevweek: function () {
            var curWeek = this.$root.week[1];
            var curYear = this.$root.week[0];
            curWeek--;
            if (curWeek < 1) {
                curYear--;
                curWeek = getISOWeeks(curYear);
            }
            this.$root.week = [curYear, curWeek];
            this.$root.loading++;
            this.$root.reload({focus: '#'+this.id});
        },
        nextweek: function () {
            var curWeek = this.$root.week[1];
            var curYear = this.$root.week[0];
            curWeek++;
            if (curWeek > getISOWeeks(curYear)) {
                curWeek = 1;
                curYear++;
            }
            this.$root.week = [curYear, curWeek];
            this.$root.loading++;
            this.$root.reload({focus: '#'+this.id});
        }
    },
});

Vue.component('pretix-widget', {
    template: ('<div class="pretix-widget-wrapper" ref="wrapper" tabindex="0" role="article" v-bind:aria-label="$root.name">'
        + '<div :class="classObject">'
        + shared_loading_fragment
        + '<div class="pretix-widget-error-message" v-if="$root.error && $root.view !== \'event\'">{{ $root.error }}</div>'
        + '<div class="pretix-widget-error-action" v-if="$root.error && $root.connection_error"><a :href="$root.newTabTarget" class="pretix-widget-button" target="_blank">'
        + strings['open_new_tab']
        + '</a></div>'
        + '<pretix-widget-event-form ref="formcomp" v-if="$root.view === \'event\'"></pretix-widget-event-form>'
        + '<pretix-widget-event-list v-if="$root.view === \'events\'"></pretix-widget-event-list>'
        + '<pretix-widget-event-calendar v-if="$root.view === \'weeks\'"></pretix-widget-event-calendar>'
        + '<pretix-widget-event-week-calendar v-if="$root.view === \'days\'"></pretix-widget-event-week-calendar>'
        + '<div class="pretix-widget-clear"></div>'
        + '<div class="pretix-widget-attribution" v-if="$root.poweredby" v-html="$root.poweredby">'
        + '</div>'
        + '</div>'
        + '</div>'
        + '</div>'
    ),
    data: shared_widget_data,
    methods: shared_methods,
    mounted: function () {
        var thisObj = this;
        if ("ResizeObserver" in window) {
            var resizeObserver = new ResizeObserver(function(entries) {
                thisObj.mobile = entries[0].contentRect.width <= 800;
            });
            resizeObserver.observe(this.$refs.wrapper);
        } else {
            this.mobile = this.$refs.wrapper.clientWidth <= 800;
            var debounce;
            window.addEventListener("resize", function() {
                if (debounce) clearTimeout(debounce);
                debounce = setTimeout(function () {
                    thisObj.mobile = thisObj.$refs.wrapper.clientWidth <= 800;
                }, 100);
            });
        }
    },
    computed: {
        classObject: function () {
            return {
                'pretix-widget': true,
                'pretix-widget-mobile': this.mobile,
                'pretix-widget-use-custom-spinners': true,
            };
        }
    }
});

Vue.component('pretix-button', {
    template: ('<div class="pretix-widget-wrapper">'
        + '<div class="pretix-widget-button-container">'
        + '<form :method="$root.formMethod" :action="$root.formAction" ref="form" :target="$root.formTarget">'
        + '<input type="hidden" name="_voucher_code" :value="$root.voucher_code" v-if="$root.voucher_code">'
        + '<input type="hidden" name="voucher" :value="$root.voucher_code" v-if="$root.voucher_code">'
        + '<input type="hidden" name="subevent" :value="$root.subevent" />'
        + '<input type="hidden" name="locale" :value="$root.lang" />'
        + '<input type="hidden" name="widget_data" :value="$root.widget_data_json" />'
        + '<input v-if="$root.consent_parameter_value" type="hidden" name="consent" :value="$root.consent_parameter_value" />'
        + '<input type="hidden" v-for="item in $root.items" :name="item.item" :value="item.count" />'
        + '<button class="pretix-button" @click="buy" v-html="$root.button_text"></button>'
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
        var url = event.target.attributes.href.value;
        if (this.$root.additionalURLParams) {
            if (url.indexOf('?')) {
                url += '&' + this.$root.additionalURLParams;
            } else {
                url += '?' + this.$root.additionalURLParams;
            }
        }
        if (this.$root.useIframe) {
            event.preventDefault();
            if (url.indexOf('?')) {
                url += '&iframe=1';
            } else {
                url += '?iframe=1';
            }
            this.$root.overlay.frame_src = url;
        } else {
            event.target.href = url;
            return;
        }
    },
    trigger_load_callback: function () {
        this.$nextTick(function () {
            for (var i = 0; i < window.PretixWidget._loaded.length; i++) {
                window.PretixWidget._loaded[i]()
            }
        });
    },
    trigger_close_callback: function () {
        this.$nextTick(function () {
            for (var i = 0; i < window.PretixWidget._closed.length; i++) {
                window.PretixWidget._closed[i]()
            }
        });
    },
    reload: function (opt = {}) {
        var url;
        if (this.$root.is_button) {
            return;
        }
        if (this.$root.subevent) {
            url = this.$root.target_url + this.$root.subevent + '/widget/product_list?lang=' + lang;
        } else {
            url = this.$root.target_url + 'widget/product_list?lang=' + lang;
        }
        if (this.$root.offset) {
            url += '&offset=' + this.$root.offset;
        }
        if (this.$root.filter) {
            url += '&' + this.$root.filter;
        }
        if (this.$root.item_filter) {
            url += '&items=' + encodeURIComponent(this.$root.item_filter);
        }
        if (this.$root.category_filter) {
            url += '&categories=' + encodeURIComponent(this.$root.category_filter);
        }
        if (this.$root.variation_filter) {
            url += '&variations=' + encodeURIComponent(this.$root.variation_filter);
        }
        var cart_id = getCookie(this.cookieName);
        if (this.$root.voucher_code) {
            url += '&voucher=' + encodeURIComponent(this.$root.voucher_code);
        }
        if (cart_id) {
            url += "&cart_id=" + encodeURIComponent(cart_id);
        }
        if (this.$root.date !== null) {
            url += "&date=" + this.$root.date.substr(0, 7);
        } else if (this.$root.week !== null) {
            url += "&date=" + this.$root.week[0] + "-W" + this.$root.week[1];
        }
        if (this.$root.style !== null) {
            url = url + '&style=' + encodeURIComponent(this.$root.style);
        }
        var root = this.$root;
        api._getJSON(url, function (data, xhr) {
            if (typeof xhr.responseURL !== "undefined") {
                var new_url = xhr.responseURL.substr(0, xhr.responseURL.indexOf("/widget/product_list?") + 1);
                var old_url = url.substr(0, url.indexOf("/widget/product_list?") + 1);
                if (new_url !== old_url) {
                    if (root.subevent) {
                        new_url = new_url.substr(0, new_url.lastIndexOf("/", new_url.length - 1) + 1);
                    }
                    root.target_url = new_url;
                    root.reload();
                    return;
                }
            }
            root.connection_error = false;
            if (data.weeks !== undefined) {
                root.weeks = data.weeks;
                root.date = data.date;
                root.week = null;
                root.events = undefined;
                root.view = "weeks";
                root.name = data.name;
                root.frontpage_text = data.frontpage_text;
                root.meta_filter_fields = data.meta_filter_fields;
            } else if (data.days !== undefined) {
                root.days = data.days;
                root.date = null;
                root.week = data.week;
                root.events = undefined;
                root.view = "days";
                root.name = data.name;
                root.frontpage_text = data.frontpage_text;
                root.meta_filter_fields = data.meta_filter_fields;
            } else if (data.events !== undefined) {
                root.events = root.append_events && root.events ? root.events.concat(data.events) : data.events;
                root.append_events = false;
                root.weeks = undefined;
                root.view = "events";
                root.name = data.name;
                root.frontpage_text = data.frontpage_text;
                root.has_more_events = data.has_more_events;
                root.meta_filter_fields = data.meta_filter_fields;
            } else {
                root.view = "event";
                // Replace target_url and subevent with canonical values in case they were slightly wrong
                root.target_url = data.target_url;
                root.subevent = data.subevent;
                // Event data
                root.name = data.name;
                root.frontpage_text = data.frontpage_text;
                root.date_range = data.date_range;
                root.location = data.location;
                root.categories = data.items_by_category;
                root.currency = data.currency;
                root.display_net_prices = data.display_net_prices;
                root.voucher_explanation_text = data.voucher_explanation_text;
                root.error = data.error;
                root.display_add_to_cart = data.display_add_to_cart;
                root.waiting_list_enabled = data.waiting_list_enabled;
                root.show_variations_expanded = data.show_variations_expanded || !!root.variation_filter;
                root.cart_id = cart_id;
                root.cart_exists = data.cart_exists;
                root.vouchers_exist = data.vouchers_exist;
                root.has_seating_plan = data.has_seating_plan;
                root.has_seating_plan_waitinglist = data.has_seating_plan_waitinglist;
                root.itemnum = data.itemnum;
            }
            root.poweredby = data.poweredby;
            if (root.loading > 0) {
                root.loading--;
                root.trigger_load_callback();
            }
            if (root.parent_stack.length > 0 && root.has_seating_plan && root.categories.length === 0 && !root.frame_dismissed && root.useIframe && !root.error && !root.has_seating_plan_waitinglist) {
                // If we're on desktop and someone selects a seating-only event in a calendar, let's open it right away,
                // but only if the person didn't close it before.
                root.startseating()
            } else {
                // make sure to only move focus to content element when it had focus before the reload/click
                // this is needed because reload is also called on initial load and we do not want to move focus on initial load
                if (root.$el.contains(document.activeElement)) {
                    root.$nextTick(function() {
                        // wait for redraw, then focus content element for better a11y
                        (opt.focus ? document.querySelector(opt.focus) : root.$el).focus();
                    });
                }
            }
        }, function (error) {
            root.categories = [];
            root.currency = '';
            if (error.status === 429) {
                root.error = strings['loading_error_429'];
                root.connection_error = true;
            } else {
                root.error = strings['loading_error'];
                root.connection_error = true;
            }
            if (root.loading > 0) {
                root.loading--;
                root.trigger_load_callback();
            }
        });
    },
    startwaiting: function () {
        var redirect_url = this.$root.target_url + 'w/' + widget_id + '/waitinglist/?iframe=1&locale=' + lang;
        if (this.$root.subevent){
            redirect_url += '&subevent=' + this.$root.subevent;
        }
        if (this.$root.additionalURLParams) {
            redirect_url += '&' + this.$root.additionalURLParams;
        }
        if (this.$root.useIframe) {
            this.$root.overlay.frame_src = redirect_url;
        } else {
            window.open(redirect_url);
        }
    },
    startseating: function () {
        var redirect_url = this.$root.target_url + 'w/' + widget_id;
        if (this.$root.subevent){
            redirect_url += '/' + this.$root.subevent;
        }
        redirect_url += '/seatingframe/?iframe=1&locale=' + lang;
        if (this.$root.voucher_code) {
            redirect_url += '&voucher=' + encodeURIComponent(this.$root.voucher_code);
        }
        if (this.$root.cart_id) {
            redirect_url += '&take_cart_id=' + this.$root.cart_id;
        }
        if (this.$root.widget_data) {
            redirect_url += '&widget_data=' + encodeURIComponent(this.$root.widget_data_json);
        }
        if (this.$root.additionalURLParams) {
            redirect_url += '&' + this.$root.additionalURLParams;
        }
        redirect_url += this.$root.consent_parameter;
        if (this.$root.useIframe) {
            this.$root.overlay.frame_src = redirect_url;
        } else {
            window.open(redirect_url);
        }
    },
    choose_event: function (event) {
        this.$root.target_url = event.event_url;
        this.$root.error = null;
        this.$root.connection_error = false;
        this.$root.subevent = event.subevent;
        this.$root.loading++;
        this.$root.reload();
    }
};

var shared_root_computed = {
    cookieName: function () {
        return "pretix_widget_" + this.target_url.replace(/[^a-zA-Z0-9]+/g, "_");
    },
    formTarget: function () {
        var is_firefox = navigator.userAgent.toLowerCase().indexOf('firefox') > -1;
        var is_android = navigator.userAgent.toLowerCase().indexOf("android") > -1;
        if (is_android && is_firefox) {
            // Opening a POST form in a new browser fails in Firefox. This is supposed to be fixed since FF 76
            // but for some reason, it is still the case in FF for Android.
            // https://bugzilla.mozilla.org/show_bug.cgi?id=1629441
            // https://github.com/pretix/pretix/issues/1040
            return "_top";
        } else {
            return "_blank";
        }
    },
    voucherFormTarget: function () {
        var form_target = this.target_url + 'w/' + widget_id + '/redeem?iframe=1&locale=' + lang;
        var cookie = getCookie(this.cookieName);
        if (cookie) {
            form_target += "&take_cart_id=" + cookie;
        }
        if (this.subevent) {
            form_target += "&subevent=" + this.subevent;
        }
        if (this.$root.widget_data) {
            form_target += '&widget_data=' + encodeURIComponent(this.$root.widget_data_json);
        }
        form_target += this.$root.consent_parameter;
        if (this.$root.additionalURLParams) {
            form_target += '&' + this.$root.additionalURLParams;
        }
        return form_target;
    },
    formMethod: function () {
        if (!this.useIframe && this.is_button && this.items.length === 0) {
            return 'get';
        }
        return 'post';
    },
    formAction: function () {
        if (!this.useIframe && this.is_button && this.items.length === 0) {
            var target;
            if (this.voucher_code) {
                target = this.target_url + 'redeem';
            } else if (this.subevent) {
                target = this.target_url + this.subevent + '/';
            } else {
                target = this.target_url;
            }
            return target;
        }
        var checkout_url = "/" + this.target_url.replace(/^[^\/]+:\/\/([^\/]+)\//, "") + "w/" + widget_id + "/";
        if (!this.$root.cart_exists) {
            checkout_url += "checkout/start";
        }
        if (this.$root.additionalURLParams) {
            checkout_url += '?' + this.$root.additionalURLParams;
        }
        var form_target = this.target_url + 'w/' + widget_id + '/cart/add?iframe=1&next=' + encodeURIComponent(checkout_url);
        var cookie = getCookie(this.cookieName);
        if (cookie) {
            form_target += "&take_cart_id=" + cookie;
        }
        form_target += this.$root.consent_parameter
        return form_target
    },
    newTabTarget: function () {
        var target = this.target_url;
        if (this.subevent) {
            target = this.target_url + this.subevent + '/';
        }
        return target;
    },
    useIframe: function () {
        if (window.crossOriginIsolated === true) {
            console.warn("pretix Widget cannot use iframe due to Cross-Origin-Embed-Policy")
            return false;
        }
        return !this.disable_iframe && (this.skip_ssl || site_is_secure());
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
                    has_priced = has_priced || item.price.gross != "0.00" || item.free_price;
                }
            }
        }
        return has_priced || cnt_items > 1;
    },
    consent_parameter_value: function () {
        if (typeof this.widget_data["consent"] !== "undefined") {
            return encodeURIComponent(this.widget_data["consent"]);
        }
        return "";
    },
    consent_parameter: function () {
        if (typeof this.widget_data["consent"] !== "undefined") {
            return "&consent=" + encodeURIComponent(this.widget_data["consent"]);
        }
        return "";
    },
    widget_data_json: function () {
        var cloned_data = Object.assign({}, this.widget_data);
        if (typeof cloned_data["consent"] !== "undefined") {
            // Remove consent as we pass it differently. We still keep it as widget_data in the input to avoid breaking
            // the JS API of the widget.
            delete cloned_data["consent"];
        }
        return JSON.stringify(cloned_data);
    },
    additionalURLParams: function () {
        if (!window.location.search.indexOf('utm_')) {
            return '';
        }
        var params = new URLSearchParams(window.location.search);
        for (var [key, value] of params.entries()) {
            if (!key.startsWith('utm_')) {
                params.delete(key);
            }
        }
        return params.toString();
    },
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
                error_url_after_new_tab: true,
                error_message: null,
                lightbox: null,
                prevActiveElement: null,
            }
        },
        props: {
            frame_src: String,
        },
        methods: {
        },
        watch: {
            frame_src: function (newValue, oldValue) {
                // show loading spinner only when previously no frame_src was set
                if (newValue && !oldValue) {
                    this.frame_loading = true;
                }
                // to close and unload the iframe, frame_src can be empty -> make it valid HTML with about:blank
                this.$el.querySelector("iframe").src = newValue || "about:blank";
            },
            frame_loading: function (newValue) {
                var dialog = this.$el?.querySelector('dialog.pretix-widget-frame-holder');
                if (newValue) {
                    if (!dialog.open) {
                        dialog.showModal();
                    }
                } else {
                    if (!this.frame_src && dialog.open) {// finished loading, but no iframe to display => close
                        dialog.close();
                    }
                }
            },
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

var create_widget = function (element, html_id=null) {
    var target_url = element.attributes.event.value;
    if (!target_url.match(/\/$/)) {
        target_url += "/";
    }
    var voucher = element.attributes.voucher ? element.attributes.voucher.value : null;
    var subevent = element.attributes.subevent ? element.attributes.subevent.value : null;
    var style = element.attributes["list-type"] ? element.attributes["list-type"].value : (element.attributes.style ? element.attributes.style.value : null);
    var skip_ssl = element.attributes["skip-ssl-check"] ? true : false;
    var disable_iframe = element.attributes["disable-iframe"] ? true : false;
    var disable_vouchers = element.attributes["disable-vouchers"] ? true : false;
    var disable_filters = element.attributes["disable-filters"] ? true : false;
    var display_event_info = element.getAttribute("display-event-info"); // null means "auto" (as before), everything other than "false" is true
    if (display_event_info !== null && display_event_info !== "auto") {
        display_event_info = display_event_info !== "false";
    } else {
        display_event_info = null;
    }
    var widget_data = JSON.parse(JSON.stringify(window.PretixWidget.widget_data));
    var filter = element.attributes.filter ? element.attributes.filter.value : null;
    var items = element.attributes.items ? element.attributes.items.value : null;
    var variations = element.attributes.variations ? element.attributes.variations.value : null;
    var categories = element.attributes.categories ? element.attributes.categories.value : null;
    for (var i = 0; i < element.attributes.length; i++) {
        var attrib = element.attributes[i];
        if (attrib.name.match(/^data-.*$/)) {
            widget_data[attrib.name.replace(/^data-/, '')] = attrib.value;
        }
    }
    html_id = html_id || element.id || makeid(16);

    var observer = new MutationObserver((mutationList) => {
        mutationList.forEach((mutation) => {
            if (mutation.type == "attributes" && mutation.attributeName.startsWith("data-")) {
                Vue.set(app.widget_data, mutation.attributeName.substring(5), mutation.target.getAttribute(mutation.attributeName));
            }
        });
    });
    var observerOptions = { attributes: true };

    if (element.tagName !== "pretix-widget") {
        element.innerHTML = "<pretix-widget></pretix-widget>";
        // we need to watch the container as well as the replaced root-node (see mounted())
        observer.observe(element, observerOptions);
    }

    var app = new Vue({
        el: element,
        data: function () {
            return {
                target_url: target_url,
                parent_stack: [],
                subevent: subevent,
                is_button: false,
                categories: null,
                currency: null,
                name: null,
                date_range: null,
                location: null,
                offset: 0,
                has_more_events: false,
                append_events: false,
                frontpage_text: null,
                filter: filter,
                item_filter: items,
                category_filter: categories,
                variation_filter: variations,
                voucher_code: voucher,
                display_net_prices: false,
                voucher_explanation_text: null,
                show_variations_expanded: !!variations,
                skip_ssl: skip_ssl,
                disable_iframe: disable_iframe,
                style: style,
                connection_error: false,
                error: null,
                weeks: null,
                days: null,
                date: null,
                week: null,
                frame_dismissed: false,
                events: null,
                view: null,
                display_add_to_cart: false,
                widget_data: widget_data,
                loading: 1,
                widget_id: 'pretix-widget-' + widget_id,
                html_id: html_id,
                vouchers_exist: false,
                disable_vouchers: disable_vouchers,
                disable_filters: disable_filters,
                display_event_info: display_event_info,
                cart_exists: false,
                itemcount: 0,
                overlay: null,
                poweredby: "",
                has_seating_plan: false,
                has_seating_plan_waitinglist: false,
                meta_filter_fields: [],
            }
        },
        created: function () {
            this.reload();
        },
        mounted: function () {
            observer.observe(this.$el, observerOptions);
        },
        computed: shared_root_computed,
        methods: shared_root_methods,
        watch: {
            'view': function (newValue, oldValue) {
                if (oldValue) {
                    // always make sure the widget is scrolled to the top
                    // as we only check top, we do not need to wait for a redraw
                    var rect = this.$el.getBoundingClientRect();
                    if (rect.top < 0) {
                        this.$el.scrollIntoView();
                    }
                }
            }
        }
    });
    create_overlay(app);
    return app;
};

var create_button = function (element, html_id=null) {
    var target_url = element.attributes.event.value;
    if (!target_url.match(/\/$/)) {
        target_url += "/";
    }
    var voucher = element.attributes.voucher ? element.attributes.voucher.value : null;
    var subevent = element.attributes.subevent ? element.attributes.subevent.value : null;
    var raw_items = element.attributes.items ? element.attributes.items.value : "";
    var skip_ssl = element.attributes["skip-ssl-check"] ? true : false;
    var disable_iframe = element.attributes["disable-iframe"] ? true : false;
    var button_text = element.innerHTML;
    var widget_data = JSON.parse(JSON.stringify(window.PretixWidget.widget_data));
    for (var i = 0; i < element.attributes.length; i++) {
        var attrib = element.attributes[i];
        if (attrib.name.match(/^data-.*$/)) {
            widget_data[attrib.name.replace(/^data-/, '')] = attrib.value;
        }
    }
    html_id = html_id || element.id || makeid(16);

    var observer = new MutationObserver((mutationList) => {
        mutationList.forEach((mutation) => {
            if (mutation.type == "attributes" && mutation.attributeName.startsWith("data-")) {
                Vue.set(app.widget_data, mutation.attributeName.substring(5), mutation.target.getAttribute(mutation.attributeName));
            }
        });
    });
    var observerOptions = { attributes: true };

    if (element.tagName !== "pretix-button") {
        element.innerHTML = "<pretix-button>" + element.innerHTML + "</pretix-button>";
        // Vue does not replace the container, so watch container as well
        observer.observe(element, observerOptions);
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
                target_url: target_url,
                subevent: subevent,
                is_button: true,
                skip_ssl: skip_ssl,
                disable_iframe: disable_iframe,
                voucher_code: voucher,
                items: items,
                error: null,
                filter: null,
                frame_dismissed: false,
                widget_data: widget_data,
                widget_id: 'pretix-widget-' + widget_id,
                html_id: html_id,
                button_text: button_text
            }
        },
        created: function () {
        },
        mounted: function () {
            observer.observe(this.$el, observerOptions);
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
window.PretixWidget._loaded = [];
window.PretixWidget._closed = [];
window.PretixWidget.addLoadListener = function (f) {
    window.PretixWidget._loaded.push(f);
}
window.PretixWidget.addCloseListener = function (f) {
    window.PretixWidget._closed.push(f);
}
window.PretixWidget.buildWidgets = function () {
    document.createElement("pretix-widget");
    document.createElement("pretix-button");
    docReady(function () {
        var widgets = document.querySelectorAll("pretix-widget, div.pretix-widget-compat");
        var wlength = widgets.length;
        for (var i = 0; i < wlength; i++) {
            var widget = widgets[i];
            widgetlist.push(create_widget(widget, widget.id || "pretix-widget-"+i));
        }

        var buttons = document.querySelectorAll("pretix-button, div.pretix-button-compat");
        var blength = buttons.length;
        for (var i = 0; i < blength; i++) {
            var button = buttons[i];
            buttonlist.push(create_button(button, button.id || "pretix-button-"+i));
        }
    });
};

window.PretixWidget.open = function (target_url, voucher, subevent, items, widget_data, skip_ssl_check, disable_iframe) {
    if (!target_url.match(/\/$/)) {
        target_url += "/";
    }

    var all_widget_data = JSON.parse(JSON.stringify(window.PretixWidget.widget_data));
    if (widget_data) {
        Object.keys(widget_data).forEach(function(key) { all_widget_data[key] = widget_data[key]; });
    }
    var root = document.createElement("div");
    document.body.appendChild(root);
    root.classList.add("pretix-widget-hidden");
    root.innerHTML = "<pretix-button ref='btn'></pretix-button>";
    var app = new Vue({
        el: root,
        data: function () {
            return {
                target_url: target_url,
                subevent: subevent || null,
                is_button: true,
                skip_ssl: skip_ssl_check || false,
                disable_iframe: disable_iframe || false,
                voucher_code: voucher || null,
                items: items || [],
                error: null,
                filter: null,
                frame_dismissed: false,
                widget_data: all_widget_data,
                widget_id: 'pretix-widget-' + widget_id,
                button_text: ""
            }
        },
        created: function () {
        },
        computed: shared_root_computed,
        methods: shared_root_methods
    });
    create_overlay(app);
    app.$nextTick(function () {
        if (this.$root.useIframe) {
            this.$refs.btn.buy();
        } else {
            this.$refs.btn.$refs.form.submit();
        }
    })
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
