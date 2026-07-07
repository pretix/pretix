export function convertToDNF (rules) {
	// Converts a set of rules to disjunctive normal form, i.e. returns something of the form
	// `(a AND b AND c) OR (a AND d AND f)`
	// without further nesting.
	if (typeof rules !== 'object' || Array.isArray(rules) || rules === null) {
		return rules
	}

	function _distribute_or_over_and (r) {
		let operator = Object.keys(r)[0]
		let values = r[operator]
		if (operator === 'and') {
			let arg_to_distribute = null
			let other_args = []
			for (let arg of values) {
				if (typeof arg === 'object' && !Array.isArray(arg) && typeof arg['or'] !== 'undefined' && arg_to_distribute === null) {
					arg_to_distribute = arg
				} else {
					other_args.push(arg)
				}
			}
			if (arg_to_distribute === null) {
				return r
			}
			let or_operands = []
			for (let dval of arg_to_distribute['or']) {
				or_operands.push({ and: other_args.concat([dval]) })
			}
			return {
				or: or_operands
			}
		} else if (!operator) {
			return r
		} else if (operator === '!' || operator === '!!' || operator === '?:' || operator === 'if') {
			console.warn('Operator ' + operator + ' currently unsupported by convert_to_dnf')
			return r
		} else {
			return r
		}
	}

	function _simplify_chained_operators (r) {
		// Simplify `(a OR b) OR (c or d)` to `a OR b OR c OR d` and the same with `AND`
		if (typeof r !== 'object' || Array.isArray(r)) {
			return r
		}
		let operator = Object.keys(r)[0]
		let values = r[operator]
		if (operator !== 'or' && operator !== 'and') {
			return r
		}
		let new_values = []
		for (let v of values) {
			if (typeof v !== 'object' || Array.isArray(v) || typeof v[operator] === 'undefined') {
				new_values.push(v)
			} else {
				new_values.push(...v[operator])
			}
		}
		let result = {}
		result[operator] = new_values
		return result
	}

	// Run _distribute_or_over_and on until it no longer changes anything. Do so recursively
	// for the full expression tree.
	let old_rules = rules
	while (true) {
		rules = _distribute_or_over_and(rules)
		let operator = Object.keys(rules)[0]
		let values = rules[operator]
		let no_list = false
		if (!Array.isArray(values)) {
			values = [values]
			no_list = true
		}
		rules = {}
		if (!no_list) {
			rules[operator] = []
			for (let v of values) {
				rules[operator].push(convertToDNF(v))
			}
		} else {
			rules[operator] = convertToDNF(values[0])
		}
		if (JSON.stringify(old_rules) === JSON.stringify(rules)) { // Let's hope this is good enough...
			break
		}
		old_rules = rules
	}
	rules = _simplify_chained_operators(rules)
	return rules
}
