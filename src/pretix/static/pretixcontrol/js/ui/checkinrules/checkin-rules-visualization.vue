<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { rules } from './django-interop'
import VizNode from './viz-node.vue'

declare const d3: any

const svg = ref<SVGSVGElement | null>(null)
const maximized = ref(false)
const zoom = ref<any>(null)
const defaultScale = ref(1)
const zoomTransform = ref(d3.zoomTransform({ k: 1, x: 0, y: 0 }))

const boxWidth = 300
const boxHeight = 62
const paddingX = 50
const marginX = 50
const marginY = 20

interface GraphNode {
	rule: any
	column: number
	children: string[]
	y?: number
	parent?: GraphNode
}

interface Graph {
	nodes_by_id: Record<string, GraphNode>
	children: string[]
	columns: number
	height: number
	y?: number
}

const graph = computed<Graph>(() => {
	/**
	 * Converts a JSON logic rule into a "flow chart".
	 *
	 * A JSON logic rule has a structure like an operator tree:
	 *
	 *  OR
	 *  |-- AND
	 *      |-- A
	 *      |-- B
	 *  |-- AND
	 *      |-- OR
	 *          |-- C
	 *          |-- D
	 *      |-- E
	 *
	 * For our visualization, we want to visualize that tree as a graph one can follow along to reach a
	 * decision, which has the structure of a directed graph:
	 *
	 *         --- A --- B --- OK!
	 *       /
	 *      /
	 *     /
	 *  --
	 *     \
	 *      \       --- C ---
	 *       \    /           \
	 *        ---              --- E --- OK!
	 *            \           /
	 *              --- D ---
	 */
	const graphData: Graph = {
		nodes_by_id: {},
		children: [],
		columns: -1,
		height: 1,
	}

	// Step 1: Start building the graph by finding all nodes and edges
	let counter = 0
	const _add_to_graph = (rule: any): [string[], string[]] => { // returns [heads, tails]
		if (typeof rule !== 'object' || rule === null) {
			const node_id = (counter++).toString()
			graphData.nodes_by_id[node_id] = {
				rule: rule,
				column: -1,
				children: [],
			}
			return [[node_id], [node_id]]
		}

		const operator = Object.keys(rule)[0]
		const operands = rule[operator]

		if (operator === 'and') {
			let children: string[] = []
			let tails: string[] | null = null
			operands.reverse()
			for (const operand of operands) {
				const [new_children, new_tails] = _add_to_graph(operand)
				for (const new_child of new_tails) {
					graphData.nodes_by_id[new_child].children.push(...children)
					for (const c of children) {
						graphData.nodes_by_id[c].parent = graphData.nodes_by_id[new_child]
					}
				}
				if (tails === null) {
					tails = new_tails
				}
				children = new_children
			}
			return [children, tails!]
		} else if (operator === 'or') {
			const children: string[] = []
			const tails: string[] = []
			for (const operand of operands) {
				const [new_children, new_tails] = _add_to_graph(operand)
				children.push(...new_children)
				tails.push(...new_tails)
			}
			return [children, tails]
		} else {
			const node_id = (counter++).toString()
			graphData.nodes_by_id[node_id] = {
				rule: rule,
				column: -1,
				children: [],
			}
			return [[node_id], [node_id]]
		}
	}
	graphData.children = _add_to_graph(JSON.parse(JSON.stringify(rules.value)))[0]

	// Step 2: We compute the "column" of every node, which is the maximum number of hops required to reach the
	// node from the root node
	const _set_column_to_min = (nodes: GraphNode[], mincol: number) => {
		for (const node of nodes) {
			if (mincol > node.column) {
				node.column = mincol
				graphData.columns = Math.max(mincol + 1, graphData.columns)
				_set_column_to_min(node.children.map(nid => graphData.nodes_by_id[nid]), mincol + 1)
			}
		}
	}
	_set_column_to_min(graphData.children.map(nid => graphData.nodes_by_id[nid]), 0)

	// Step 3: Align each node on a grid. The x position is already given by the column computed above, but we still
	// need the y position. This part of the algorithm is opinionated and probably not yet the nicest solution we
	// can use!
	const _set_y = (node: Graph | GraphNode, offset: number): number => {
		if (typeof node.y === 'undefined') {
			// We only take the first value we found for each node
			node.y = offset
		}

		let used = 0
		for (const cid of node.children) {
			used += Math.max(0, _set_y(graphData.nodes_by_id[cid], offset + used) - 1)
			used++
		}
		return used
	}
	_set_y(graphData, 0)

	// Step 4: Compute the "height" of the graph by looking at the node with the highest y value
	graphData.height = 1
	for (const node of [...Object.values(graphData.nodes_by_id)]) {
		graphData.height = Math.max(graphData.height, (node.y ?? 0) + 1)
	}

	return graphData
})

const contentWidth = computed(() => {
	return graph.value.columns * (boxWidth + marginX) + 2 * paddingX
})

const contentHeight = computed(() => {
	return graph.value.height * (boxHeight + marginY)
})

const viewBox = computed(() => {
	return `0 0 ${contentWidth.value} ${contentHeight.value}`
})

function createZoom () {
	if (!svg.value) return

	const viewportHeight = svg.value.clientHeight
	const viewportWidth = svg.value.clientWidth
	defaultScale.value = 1

	zoom.value = d3
		.zoom()
		.scaleExtent([Math.min(defaultScale.value * 0.5, 1), Math.max(5, contentHeight.value / viewportHeight, contentWidth.value / viewportWidth)])
		.extent([[0, 0], [viewportWidth, viewportHeight]])
		.filter((event: any) => {
			const wheeled = event.type === 'wheel'
			const mouseDrag
				= event.type === 'mousedown'
					|| event.type === 'mouseup'
					|| event.type === 'mousemove'
			const touch
				= event.type === 'touchstart'
					|| event.type === 'touchmove'
					|| event.type === 'touchstop'
			return (wheeled || mouseDrag || touch) && maximized.value
		})
		.wheelDelta((event: any) => {
			// In contrast to default implementation, do not use a factor 10 if ctrl is pressed
			return -event.deltaY * (event.deltaMode === 1 ? 0.05 : event.deltaMode ? 1 : 0.002)
		})
		.on('zoom', (event: any) => {
			zoomTransform.value = event.transform
		})

	const initTransform = d3.zoomIdentity
		.scale(defaultScale.value)
		.translate(0, 0)
	zoomTransform.value = initTransform

	// This sets correct d3 internal state for the initial centering
	d3.select(svg.value)
		.call(zoom.value.transform, initTransform)

	const svgSelection = d3.select(svg.value).call(zoom.value)
	svgSelection.on('touchmove.zoom', null)
	// TODO touch support
}

watch(maximized, () => {
	nextTick(() => {
		createZoom()
	})
})

onMounted(() => {
	createZoom()
	window.addEventListener('resize', createZoom)
})

onUnmounted(() => {
	window.removeEventListener('resize', createZoom)
})

</script>
<template lang="pug">
div(:class="'checkin-rules-visualization ' + (maximized ? 'maximized' : '')")
	.tools
		button.btn.btn-default(
			v-if="maximized",
			type="button",
			@click.prevent="maximized = false"
		)
			span.fa.fa-window-close
		button.btn.btn-default(
			v-if="!maximized",
			type="button",
			@click.prevent="maximized = true"
		)
			span.fa.fa-window-maximize
	svg(
		ref="svg",
		:width="contentWidth",
		:height="contentHeight",
		:viewBox="viewBox"
	)
		g(:transform="zoomTransform.toString()")
			VizNode(
				v-for="(node, nodeid) in graph.nodes_by_id",
				:key="nodeid",
				:node="node",
				:children="node.children.map((n: string) => graph.nodes_by_id[n])",
				:nodeid="nodeid",
				:boxWidth="boxWidth",
				:boxHeight="boxHeight",
				:marginX="marginX",
				:marginY="marginY",
				:paddingX="paddingX"
			)
</template>
