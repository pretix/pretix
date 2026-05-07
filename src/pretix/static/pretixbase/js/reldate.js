if (!window.__reldateInitialized) {
    window.__reldateInitialized = true;
    document.addEventListener('DOMContentLoaded', () => {
         const NO_BEFORE_VALUES = ['datetime'];

        document.querySelectorAll('.reldatetime, .reldate').forEach(container => {
            const groups = container.querySelectorAll('.radio');

            groups.forEach(group => {
                const selects = group.querySelectorAll('select');
                if (selects.length < 2) return;

                let referenceSelect = null;
                let beforeAfterSelect = null;

                selects.forEach(sel => {
                    const values = Array.from(sel.options).map(o => o.value);
                    // only attach to selects that contain problematic values
                    if (NO_BEFORE_VALUES.some(v => values.includes(v))) {
                        referenceSelect = sel;
                    } else if (values.includes('before') && values.includes('after')) {
                        beforeAfterSelect = sel;
                    }
                });
                if (!referenceSelect || !beforeAfterSelect) return;

                const beforeOption = beforeAfterSelect.querySelector('option[value="before"]');
                const updateBeforeOption = () => {
                    if (NO_BEFORE_VALUES.includes(referenceSelect.value)) {
                        beforeOption.disabled = true;
                        if (beforeAfterSelect.value === 'before') {
                            beforeAfterSelect.value = 'after';
                            beforeAfterSelect.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    } else {
                        beforeOption.disabled = false;
                    }
                };
                referenceSelect.addEventListener('change', updateBeforeOption);
                updateBeforeOption();
            });
        });
    });
}
