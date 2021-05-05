$(document).ready(function () {
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
  };

  Vue.component('checkin-rule', CheckinRule.default);
  var app = new Vue({
    el: '#rules-editor',
    components: {
      CheckinRulesEditor: CheckinRulesEditor.default,
      CheckinRulesVisualization: CheckinRulesVisualization.default,
    },
    data: function () {
      return {
        rules: {},
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
        },
        hasRules: false,
      };
    },
    created: function () {
      this.rules = JSON.parse($("#id_rules").val());
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
