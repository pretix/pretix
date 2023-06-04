$(function () {
  var TYPEOPS = {
    // Every change to our supported JSON logic must be done
    // * in pretix.base.services.checkin
    // * in pretix.base.models.checkin
    // * in checkinrules.js
    // * in libpretixsync
    'product': {
      'inList': {
        'label': gettext('is one of'),
        'cardinality': 2,
      }
    },
    'variation': {
      'inList': {
        'label': gettext('is one of'),
        'cardinality': 2,
      }
    },
    'datetime': {
      'isBefore': {
        'label': gettext('is before'),
        'cardinality': 2,
      },
      'isAfter': {
        'label': gettext('is after'),
        'cardinality': 2,
      },
    },
    'int': {
      '<': {
        'label': '<',
        'cardinality': 2,
      },
      '<=': {
        'label': '≤',
        'cardinality': 2,
      },
      '>': {
        'label': '>',
        'cardinality': 2,
      },
      '>=': {
        'label': '≥',
        'cardinality': 2,
      },
      '==': {
        'label': '=',
        'cardinality': 2,
      },
      '!=': {
        'label': '≠',
        'cardinality': 2,
      },
    },
  };
  var VARS = {
    'product': {
      'label': gettext('Product'),
      'type': 'product',
    },
    'variation': {
      'label': gettext('Product variation'),
      'type': 'variation',
    },
    'now': {
      'label': gettext('Current date and time'),
      'type': 'datetime',
    },
    'now_isoweekday': {
      'label': gettext('Current day of the week (1 = Monday, 7 = Sunday)'),
      'type': 'int',
    },
    'entries_number': {
      'label': gettext('Number of previous entries'),
      'type': 'int',
    },
    'entries_today': {
      'label': gettext('Number of previous entries since midnight'),
      'type': 'int',
    },
    'entries_days': {
      'label': gettext('Number of days with a previous entry'),
      'type': 'int',
    },
    'minutes_since_last_entry': {
      'label': gettext('Minutes since last entry (-1 on first entry)'),
      'type': 'int',
    },
    'minutes_since_first_entry': {
      'label': gettext('Minutes since first entry (-1 on first entry)'),
      'type': 'int',
    },
  };

  var components = {
    CheckinRulesVisualization: CheckinRulesVisualization.default,
  }
  if (typeof CheckinRule !== "undefined") {
    Vue.component('checkin-rule', CheckinRule.default);
    components = {
      CheckinRulesEditor: CheckinRulesEditor.default,
      CheckinRulesVisualization: CheckinRulesVisualization.default,
    }
  }
  var app = new Vue({
    el: '#rules-editor',
    components: components,
    data: function () {
      return {
        rules: {},
        items: [],
        all_products: false,
        limit_products: [],
        TYPEOPS: TYPEOPS,
        VARS: VARS,
        texts: {
          and: gettext('All of the conditions below (AND)'),
          or: gettext('At least one of the conditions below (OR)'),
          date_from: gettext('Event start'),
          date_to: gettext('Event end'),
          date_admission: gettext('Event admission'),
          date_custom: gettext('custom date and time'),
          date_customtime: gettext('custom time'),
          date_tolerance: gettext('Tolerance (minutes)'),
          condition_add: gettext('Add condition'),
          minutes: gettext('minutes'),
          duplicate: gettext('Duplicate'),
        },
        hasRules: false,
      };
    },
    computed: {
      missingItems: function () {
        // This computed property contains list of item or variation names that
        // a) Are allowed on the checkin list according to all_products or include_products
        // b) Are not matched by ANY logical branch of the rule.
        // The list will be empty if there is a "catch-all" rule.
        var products_seen = {};
        var variations_seen = {};
        var rules = convert_to_dnf(this.rules);
        var branch_without_product_filter = false;

        if (!rules["or"]) {
          rules = {"or": [rules]}
        }

        for (var part of rules["or"]) {
          if (!part["and"]) {
            part = {"and": [part]}
          }
          var this_branch_without_product_filter = true;
          for (var subpart of part["and"]) {
            if (subpart["inList"]) {
              if (subpart["inList"][0]["var"] === "product" && subpart["inList"][1]) {
                this_branch_without_product_filter = false;
                for (var listentry of subpart["inList"][1]["objectList"]) {
                  products_seen[parseInt(listentry["lookup"][1])] = true
                }
              } else if (subpart["inList"][0]["var"] === "variation" && subpart["inList"][1]) {
                this_branch_without_product_filter = false;
                for (var listentry_ of subpart["inList"][1]["objectList"]) {
                  variations_seen[parseInt(listentry_["lookup"][1])] = true
                }
              }
            }
          }
          if (this_branch_without_product_filter) {
            branch_without_product_filter = true;
            break;
          }
        }
        if (branch_without_product_filter || (!Object.keys(products_seen).length && !Object.keys(variations_seen).length)) {
          // At least one branch with no product filters at all – that's fine.
          return [];
        }

        var missing = [];
        for (var item of this.items) {
          if (products_seen[item.id]) continue;
          if (!this.all_products && !this.limit_products.includes(item.id)) continue;
          if (item.variations.length > 0) {
            for (var variation of item.variations) {
              if (variations_seen[variation.id]) continue;
              missing.push(item.name + " – " + variation.name)
            }
          } else {
            missing.push(item.name)
          }
        }
        return missing;
      }
    },
    created: function () {
      this.rules = JSON.parse($("#id_rules").val());
      if ($("#items").length) {
        this.items = JSON.parse($("#items").html());

        var root = this.$root

        function _update() {
          root.all_products = $("#id_all_products").prop("checked")
          root.limit_products = $("input[name=limit_products]:checked").map(function () {
            return parseInt($(this).val())
          }).toArray()
        }

        $("#id_all_products, input[name=limit_products]").on("change", function () {
          _update();
        })
        _update()
      }
    },
    watch: {
      rules: {
        deep: true,
        handler: function (newval) {
          $("#id_rules").val(JSON.stringify(newval));
        }
      },
    }
  })
});
