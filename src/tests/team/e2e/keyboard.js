// Keyboard helpers: describe the focused element and move focus with real Tab key presses.

/** Short, stable description of document.activeElement: the form field name, or the visible text. */
export async function focused(page) {
    return page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return 'body';
        if (el.name) return el.name;
        return (el.textContent || el.value || '').trim().replace(/\s+/g, ' ');
    });
}

/**
 * Press Tab until the focused element matches `target` (string = exact, RegExp = test).
 * Returns every element visited, so callers can assert the focus order.
 */
export async function tabTo(page, target, { max = 120, backwards = false } = {}) {
    const visited = [];
    const matches = (d) => (target instanceof RegExp ? target.test(d) : d === target);
    for (let i = 0; i < max; i++) {
        await page.keyboard.press(backwards ? 'Shift+Tab' : 'Tab');
        const d = await focused(page);
        visited.push(d);
        if (matches(d)) return visited;
    }
    throw new Error(`Focus never reached ${target} after ${max} Tab presses. Visited: ${visited.join(' | ')}`);
}

/** Press Tab `count` times and return the focus sequence. */
export async function tabSequence(page, count) {
    const visited = [];
    for (let i = 0; i < count; i++) {
        await page.keyboard.press('Tab');
        visited.push(await focused(page));
    }
    return visited;
}
