<script setup lang="ts">
import { computed } from 'vue'
import { TEXTS, VARS, TYPEOPS } from './constants'

declare const $: any
declare const moment: any

interface GraphNode {
	rule: any
	column: number
	children: string[]
	y: number
	parent?: GraphNode
}

const props = defineProps<{
	node: GraphNode
	nodeid: string
	children: GraphNode[]
	boxWidth: number
	boxHeight: number
	marginX: number
	marginY: number
	paddingX: number
}>()

const x = computed(() => {
	return props.node.column * (props.boxWidth + props.marginX) + props.marginX / 2 + props.paddingX
})

const y = computed(() => {
	return props.node.y * (props.boxHeight + props.marginY) + props.marginY / 2
})

const edges = computed(() => {
	const startX = x.value + props.boxWidth + 1
	const startY = y.value + props.boxHeight / 2
	return props.children.map((c) => {
		const endX = (c.column * (props.boxWidth + props.marginX) + props.marginX / 2 + props.paddingX) - 1
		const endY = (c.y * (props.boxHeight + props.marginY) + props.marginY / 2) + props.boxHeight / 2

		return `
            M ${startX} ${startY}
            L ${endX - 50} ${startY}
            C ${endX - 25} ${startY} ${endX - 25} ${startY} ${endX - 25} ${startY + 25 * Math.sign(endY - startY)}
            L ${endX - 25} ${endY - 25 * Math.sign(endY - startY)}
            C ${endX - 25} ${endY} ${endX - 25} ${endY} ${endX} ${endY}
          `
	})
})

const checkEdge = computed(() => {
	const startX = x.value + props.boxWidth + 1
	const startY = y.value + props.boxHeight / 2

	return `M ${startX} ${startY} L ${startX + 25} ${startY}`
})

const rootEdge = computed(() => {
	if (props.node.column > 0) {
		return
	}
	const startX = 0
	const startY = props.boxHeight / 2 + props.marginY / 2
	const endX = x.value - 1
	const endY = y.value + props.boxHeight / 2

	return `
            M ${startX} ${startY}
            L ${endX - 50} ${startY}
            C ${endX - 25} ${startY} ${endX - 25} ${startY} ${endX - 25} ${startY + 25 * Math.sign(endY - startY)}
            L ${endX - 25} ${endY - 25 * Math.sign(endY - startY)}
            C ${endX - 25} ${endY} ${endX - 25} ${endY} ${endX} ${endY}
        `
})

const operator = computed(() => {
	return Object.keys(props.node.rule).filter((k) => !k.startsWith('__'))[0]
})

const variable = computed(() => {
	const op = operator.value
	if (props.node.rule[op] && props.node.rule[op][0]) {
		if (props.node.rule[op][0]['entries_since']) {
			return 'entries_since'
		}
		if (props.node.rule[op][0]['entries_before']) {
			return 'entries_before'
		}
		if (props.node.rule[op][0]['entries_days_since']) {
			return 'entries_days_since'
		}
		if (props.node.rule[op][0]['entries_days_before']) {
			return 'entries_days_before'
		}
		return props.node.rule[op][0]['var']
	} else {
		return ''
	}
})

const vardata = computed(() => {
	return VARS[variable.value as keyof typeof VARS]
})

const varresult = computed(() => {
	const op = operator.value
	if (props.node.rule[op] && props.node.rule[op][0]) {
		if (typeof props.node.rule[op][0]['__result'] === 'undefined')
			return null
		return props.node.rule[op][0]['__result']
	} else {
		return ''
	}
})

const rightoperand = computed(() => {
	const op = operator.value
	if (props.node.rule[op] && typeof props.node.rule[op][1] !== 'undefined') {
		return props.node.rule[op][1]
	} else {
		return null
	}
})

const op = computed(() => {
	return TYPEOPS[vardata.value.type as keyof typeof TYPEOPS]?.[operator.value as any]
})

const operands = computed(() => {
	return props.node.rule[operator.value]
})

const result = computed(() => {
	return typeof props.node.rule.__result === 'undefined' ? null : !!props.node.rule.__result
})

const resultInclParents = computed(() => {
	if (typeof props.node.rule.__result === 'undefined') return null

	function _p (node: GraphNode): boolean {
		if (node.parent) {
			return node.rule.__result && _p(node.parent)
		}
		return node.rule.__result
	}
	return _p(props.node)
})

const nodeClass = computed(() => {
	return {
		node: true,
		'node-true': result.value === true,
		'node-false': result.value === false,
	}
})

function df (val: string) {
	const format = $('body').attr('data-datetimeformat')
	return moment(val).format(format)
}

function tf (val: string) {
	const format = $('body').attr('data-timeformat')
	return moment(val, 'HH:mm:ss').format(format)
}
</script>
<template lang="pug">
g
	path.edge(v-for="e in edges", :key="e", :d="e")
	path.edge(v-if="rootEdge", :d="rootEdge")
	path.edge(v-if="!node.children.length", :d="checkEdge")
	rect(:width="boxWidth", :height="boxHeight", :x="x", :y="y", :class="nodeClass", rx="5")

	foreignObject(:width="boxWidth - 10", :height="boxHeight - 10", :x="x + 5", :y="y + 5")
		div.text(xmlns="http://www.w3.org/1999/xhtml")
			span(v-if="vardata && vardata.type === 'int'")
				span.fa.fa-sign-in(v-if="variable.startsWith('entries_')")
				| {{ vardata.label }}
				br
				span(v-if="varresult !== null") {{ varresult }}
				strong
					| {{ op.label }} {{ rightoperand }}
			span(v-else-if="vardata && vardata.type === 'int_by_datetime'")
				span.fa.fa-sign-in(v-if="variable.startsWith('entries_')")
				| {{ vardata.label }}
				span(v-if="node.rule[operator][0][variable][0].buildTime[0] === 'custom'")
					| {{ df(node.rule[operator][0][variable][0].buildTime[1]) }}
				span(v-else-if="node.rule[operator][0][variable][0].buildTime[0] === 'customtime'")
					| {{ tf(node.rule[operator][0][variable][0].buildTime[1]) }}
				span(v-else)
					| {{ TEXTS[node.rule[operator][0][variable][0].buildTime[0]] }}
				br
				span(v-if="varresult !== null") {{ varresult }}
				strong
					| {{ op.label }} {{ rightoperand }}
			span(v-else-if="vardata && variable === 'now'")
				span.fa.fa-clock-o
				|  {{ vardata.label }}
				br
				span(v-if="varresult !== null") {{ varresult }}
				strong
					| {{ op.label }}
					br
					span(v-if="rightoperand.buildTime[0] === 'custom'")
						| {{ df(rightoperand.buildTime[1]) }}
					span(v-else-if="rightoperand.buildTime[0] === 'customtime'")
						| {{ tf(rightoperand.buildTime[1]) }}
					span(v-else)
						| {{ TEXTS[rightoperand.buildTime[0]] }}
					span(v-if="operands[2]")
						span(v-if="operator === 'isBefore'") +
						span(v-else) -
						| {{ operands[2] }}
						| {{ TEXTS.minutes }}
			span(v-else-if="vardata && operator === 'inList'")
				span.fa.fa-sign-in(v-if="variable === 'gate'")
				span.fa.fa-ticket(v-else)
				| {{ vardata.label }}
				span(v-if="varresult !== null")  ({{ varresult }})
				br
				strong
					| {{ rightoperand.objectList.map((o: any) => o.lookup[2]).join(", ") }}
			span(v-else-if="vardata && vardata.type === 'enum_entry_status'")
				span.fa.fa-check-circle-o
				| {{ vardata.label }}
				span(v-if="varresult !== null")  ({{ varresult }})
				br
				strong
					| {{ op.label }} {{ rightoperand }}

	g(v-if="result === false", :transform="`translate(${x + boxWidth - 15}, ${y - 10})`")
		ellipse(fill="#fff", cx="14.685823", cy="14.318233", rx="12.140151", ry="11.55523")
		path.error(d="M 15,0 C 23.28125,0 30,6.71875 30,15 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 Z m 2.5,24.35547 V 20.64453 C 17.5,20.29297 17.22656,20 16.89453,20 h -3.75 C 12.79297,20 12.5,20.29297 12.5,20.64453 v 3.71094 C 12.5,24.70703 12.79297,25 13.14453,25 h 3.75 C 17.22656,25 17.5,24.70703 17.5,24.35547 Z M 17.4609,17.63672 17.81246,5.50781 c 0,-0.13672 -0.0586,-0.27343 -0.19531,-0.35156 C 17.49996,5.05855 17.32418,5 17.1484,5 h -4.29688 c -0.17578,0 -0.35156,0.0586 -0.46875,0.15625 -0.13672,0.0781 -0.19531,0.21484 -0.19531,0.35156 l 0.33203,12.12891 c 0,0.27344 0.29297,0.48828 0.66406,0.48828 h 3.61329 c 0.35156,0 0.64453,-0.21484 0.66406,-0.48828 z")
	g(v-if="result === true", :transform="`translate(${x + boxWidth - 15}, ${y - 10})`")
		ellipse(fill="#fff", cx="14.685823", cy="14.318233", rx="12.140151", ry="11.55523")
		path.check(d="m 25.078125,11.835938 c 0,-0.332032 -0.117188,-0.664063 -0.351563,-0.898438 L 22.949219,9.1796875 c -0.234375,-0.234375 -0.546875,-0.3710937 -0.878907,-0.3710937 -0.332031,0 -0.644531,0.1367187 -0.878906,0.3710937 L 13.222656,17.128906 8.8085938,12.714844 C 8.5742188,12.480469 8.2617188,12.34375 7.9296875,12.34375 c -0.3320313,0 -0.6445313,0.136719 -0.8789063,0.371094 l -1.7773437,1.757812 c -0.234375,0.234375 -0.3515625,0.566407 -0.3515625,0.898438 0,0.332031 0.1171875,0.644531 0.3515625,0.878906 l 7.0703125,7.070312 c 0.234375,0.234375 0.566406,0.371094 0.878906,0.371094 0.332032,0 0.664063,-0.136719 0.898438,-0.371094 L 24.726562,12.714844 c 0.234375,-0.234375 0.351563,-0.546875 0.351563,-0.878906 z M 30,15 C 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 23.28125,0 30,6.71875 30,15 Z")
	g(v-if="!node.children.length && (resultInclParents === null || resultInclParents === true)", :transform="`translate(${x + boxWidth + 25}, ${y + boxHeight/2 - 15})`")
		path.check(d="m 25.078125,11.835938 c 0,-0.332032 -0.117188,-0.664063 -0.351563,-0.898438 L 22.949219,9.1796875 c -0.234375,-0.234375 -0.546875,-0.3710937 -0.878907,-0.3710937 -0.332031,0 -0.644531,0.1367187 -0.878906,0.3710937 L 13.222656,17.128906 8.8085938,12.714844 C 8.5742188,12.480469 8.2617188,12.34375 7.9296875,12.34375 c -0.3320313,0 -0.6445313,0.136719 -0.8789063,0.371094 l -1.7773437,1.757812 c -0.234375,0.234375 -0.3515625,0.566407 -0.3515625,0.898438 0,0.332031 0.1171875,0.644531 0.3515625,0.878906 l 7.0703125,7.070312 c 0.234375,0.234375 0.566406,0.371094 0.878906,0.371094 0.332032,0 0.664063,-0.136719 0.898438,-0.371094 L 24.726562,12.714844 c 0.234375,-0.234375 0.351563,-0.546875 0.351563,-0.878906 z M 30,15 C 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 23.28125,0 30,6.71875 30,15 Z")
	g(v-if="!node.children.length && (resultInclParents === false)", :transform="`translate(${x + boxWidth + 25}, ${y + boxHeight/2 - 15})`")
		path.error(d="M 15,0 C 23.28125,0 30,6.71875 30,15 30,23.28125 23.28125,30 15,30 6.71875,30 0,23.28125 0,15 0,6.71875 6.71875,0 15,0 Z m 2.5,24.35547 V 20.64453 C 17.5,20.29297 17.22656,20 16.89453,20 h -3.75 C 12.79297,20 12.5,20.29297 12.5,20.64453 v 3.71094 C 12.5,24.70703 12.79297,25 13.14453,25 h 3.75 C 17.22656,25 17.5,24.70703 17.5,24.35547 Z M 17.4609,17.63672 17.81246,5.50781 c 0,-0.13672 -0.0586,-0.27343 -0.19531,-0.35156 C 17.49996,5.05855 17.32418,5 17.1484,5 h -4.29688 c -0.17578,0 -0.35156,0.0586 -0.46875,0.15625 -0.13672,0.0781 -0.19531,0.21484 -0.19531,0.35156 l 0.33203,12.12891 c 0,0.27344 0.29297,0.48828 0.66406,0.48828 h 3.61329 c 0.35156,0 0.64453,-0.21484 0.66406,-0.48828 z")
</template>
