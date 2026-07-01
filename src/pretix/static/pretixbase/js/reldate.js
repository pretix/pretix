if (!window.__reldateInitialized) {
	window.__reldateInitialized = true
	document.addEventListener('DOMContentLoaded', () => {
		document.querySelectorAll('.reldatetime, .reldate').forEach(container => {
			const groups = container.querySelectorAll('.radio')

			groups.forEach(group => {
				const referenceSelect = group.querySelector('select[data-relative-choice]')
				const beforeAfterSelect = group.querySelector('select[data-relation-choice]')
				if (!referenceSelect || !beforeAfterSelect) return

				const beforeOption = beforeAfterSelect.querySelector('option[value="before"]')
				const afterOption = beforeAfterSelect.querySelector('option[value="after"]')

				const updateBeforeOption = () => {
					let supportsBefore = referenceSelect.selectedOptions[0].hasAttribute('data-supports-before')
					if (beforeOption) {
						beforeOption.disabled = !beforeOption.disabled && !supportsBefore
					}

					let supportsAfter = referenceSelect.selectedOptions[0].hasAttribute('data-supports-after')
					if (afterOption) {
						afterOption.disabled = !afterOption.disabled && !supportsAfter
					}

					let dirty = false
					if (beforeOption.disabled && beforeAfterSelect.value === 'before') {
						beforeAfterSelect.value = 'after'
						dirty = true
					}
					if (afterOption.disabled && beforeAfterSelect.value === 'after') {
						beforeAfterSelect.value = 'before'
						dirty = true
					}

					if (dirty) {
						beforeAfterSelect.dispatchEvent(new Event('change', { bubbles: true }))
					}
				}
				referenceSelect.addEventListener('change', updateBeforeOption)
				updateBeforeOption()
			})
		})
	})
}
