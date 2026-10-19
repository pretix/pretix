<script setup lang="ts">
import { inject } from "vue";
import { StoreKey } from "../../walletStore";
import { dateTimeFormat, i18nstringLocalize } from "../../helpers";
import Google from "./google.vue";
const store = inject(StoreKey)!;
const gettext = (window as any).gettext;

const props = defineProps<{ data: any }>();

function isActive(fieldgroup: string) {
    return store.layout.fieldgroups[fieldgroup]?.active;
}
</script>

<template lang="pug">
    Google(:data="data")
        template(#card-rows)
            div.card-row(v-if="isActive('date')")
                div
                    div.pass-label {{ gettext("Date") }}
                    div.pass-content {{ dateTimeFormat(data.date_from, {"dateStyle": "medium"}) }}
                div
                    div.pass-label {{ gettext("Time") }}
                    div.pass-content {{ dateTimeFormat(data.date_from, {"timeStyle": "short"}) }}
            div.card-row(v-if="isActive('seating')")
                div
                    div.pass-label {{ gettext("Section") }}
                    div.pass-content {{ gettext("Ground floor") }}
                div
                    div.pass-label {{ gettext("Row") }} / {{ gettext("Seat") }}
                    div.pass-content 5 / 2

        template(#details)
            div.pass-details-row(v-if="isActive('ticket_holder')")
                div.pass-label {{ gettext("Ticket Holder") }}
                div.pass-content {{ gettext("John Doe") }}
            div.pass-details-row(v-if="isActive('venue')")
                div.pass-label  {{ i18nstringLocalize(data.venue?.[0]) }}
                div.pass-content {{ i18nstringLocalize(data.venue?.[1]) }}
            div.pass-details-row(v-if="isActive('date')")
                div.pass-label {{ gettext("Event Start Time") }}
                div.pass-content {{ i18nstringLocalize(data.venue?.[1]) }}
            div.pass-details-row
                div.pass-label {{ gettext("Ticket Type") }}
                div.pass-content {{ gettext("Sample product") }}
            div.pass-details-row
                div.pass-label {{ gettext("Ticket Number") }}
                div.pass-content ABCDE-1
            div.pass-details-row
                div.pass-label {{ gettext("Order Number") }}
                div.pass-content ABCDE
            a.pass-details-link.f-row(:href="data.event_page")
                div
                    i.fa.fa-globe
                div.pass-label
                    | {{ " " + gettext("Website") }}

</template>