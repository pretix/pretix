/*global gettext, Vue, App*/
function gettext(msgid) {
    if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}

function ngettext(singular, plural, count) {
    if (typeof django !== 'undefined' && typeof django.ngettext !== 'undefined') {
        return django.ngettext(singular, plural, count);
    }
    return plural;
}


moment.locale(document.body.attributes['data-datetimelocale'].value)
window.vapp = new Vue({
    components: {
        App: App.default
    },
    render: function (h) {
        return h('App')
    },
    data: {
        api: {
            lists: document.querySelector('#app').attributes['data-api-lists'].value,
        },
        strings: {
            'checkinlist.select': gettext('Select a check-in list'),
            'checkinlist.none': gettext('No active check-in lists found.'),
            'checkinlist.switch': gettext('Switch check-in list'),
            'results.headline': gettext('Search results'),
            'results.none': gettext('No tickets found'),
            'check.headline': gettext('Result'),
            'check.attention': gettext('This ticket requires special attention'),
            'scantype.switch': gettext('Switch direction'),
            'scantype.entry': gettext('Entry'),
            'scantype.exit': gettext('Exit'),
            'input.placeholder': gettext('Scan a ticket or search and press return…'),
            'pagination.next': gettext('Load more'),
            'status.p': gettext('Valid'),
            'status.n': gettext('Unpaid'),
            'status.c': gettext('Canceled'),
            'status.e': gettext('Canceled'),
            'status.redeemed': gettext('Redeemed'),
            'modal.cancel': gettext('Cancel'),
            'modal.continue': gettext('Continue'),
            'modal.unpaid.head': gettext('Ticket not paid'),
            'modal.unpaid.text': gettext('This ticket is not yet paid. Do you want to continue anyways?'),
            'modal.questions': gettext('Additional information required'),
            'result.ok': gettext('Valid ticket'),
            'result.exit': gettext('Exit recorded'),
            'result.already_redeemed': gettext('Ticket already used'),
            'result.questions': gettext('Information required'),
            'result.invalid': gettext('Unknown ticket'),
            'result.product': gettext('Ticket type not allowed here'),
            'result.unpaid': gettext('Ticket not paid'),
            'result.rules': gettext('Entry not allowed'),
            'result.revoked': gettext('Ticket code revoked/changed'),
            'result.blocked': gettext('Ticket blocked'),
            'result.invalid_time': gettext('Ticket not valid at this time'),
            'result.canceled': gettext('Order canceled'),
            'result.ambiguous': gettext('Ticket code is ambiguous on list'),
            'status.checkin': gettext('Checked-in Tickets'),
            'status.position': gettext('Valid Tickets'),
            'status.inside': gettext('Currently inside'),
        },
        event_name: document.querySelector('#app').attributes['data-event-name'].value,
        timezone: document.body.attributes['data-timezone'].value,
        datetime_format: document.body.attributes['data-datetimeformat'].value,
    },
    el: '#app'
})
