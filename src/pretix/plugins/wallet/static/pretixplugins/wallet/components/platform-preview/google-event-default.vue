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
                    div.card-rows-label {{ gettext("Date") }}
                    div.card-rows-content {{ dateTimeFormat(data.date_from, {"dateStyle": "medium"}) }}
                div
                    div.card-rows-label {{ gettext("Time") }}
                    div.card-rows-content {{ dateTimeFormat(data.date_from, {"timeStyle": "short"}) }}
            div.card-row(v-if="isActive('seating')")
                div
                    div.card-rows-label {{ gettext("Section") }}
                    div.card-rows-content {{ gettext("Ground floor") }}
                div
                    div.card-rows-label {{ gettext("Row") }} / {{ gettext("Seat") }}
                    div.card-rows-content 5 / 2

        template(#details)
            div.pass-details-row(v-if="isActive('ticket_holder')")
                div.pass-details-label {{ gettext("Ticket Holder") }}
                div.pass-details-content {{ gettext("John Doe") }}
            div.pass-details-row(v-if="isActive('venue')")
                div.pass-details-label  {{ i18nstringLocalize(data.venue?.[0]) }}
                div.pass-details-content {{ i18nstringLocalize(data.venue?.[1]) }}
            div.pass-details-row(v-if="isActive('date')")
                div.pass-details-label {{ gettext("Event Start Time") }}
                div.pass-details-content {{ i18nstringLocalize(data.venue?.[1]) }}
            div.pass-details-row
                div.pass-details-label {{ gettext("Ticket Type") }}
                div.pass-details-content {{ gettext("Sample product") }}
            div.pass-details-row
                div.pass-details-label {{ gettext("Ticket Number") }}
                div.pass-details-content ABCDE-1
            div.pass-details-row
                div.pass-details-label {{ gettext("Order Number") }}
                div.pass-details-content ABCDE
            a.pass-details-link.f-row(:href="data.event_page")
                div
                    i.fa.fa-globe
                div.pass-details-label
                    | {{ " " + gettext("Website") }}

</template>