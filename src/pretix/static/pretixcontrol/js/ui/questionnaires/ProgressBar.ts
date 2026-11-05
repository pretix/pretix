export class ProgressBar {
    private static container : HTMLDivElement = ProgressBar.createContainer();
    private static indeterminateBar = null;
    private static indeterminateCtr = 0;

    private static createContainer() {
        const el = document.createElement('div')
        el.className = 'progressBar'
        document.body.appendChild(el)
        return el
    }

    static show(message?: string, max?: number) {
        if (!max) return ProgressBar.showIndeterminate();
        const bar = document.createElement('div')
        bar.className = 'progressBar_progress'
        ProgressBar.container.appendChild(bar);
        return {
            disposed: false,
            [Symbol.dispose]() {
                if (this.disposed) return;
                bar.remove();
                this.disposed = true;
            },
            set message(val: string) {
            },
            set progress(val: number) {
                bar.style.width = `${val / max * 100}%`;
            }
        };
    }

    static showIndeterminate() {
        if ((ProgressBar.indeterminateCtr++) === 0) {
            const bar = ProgressBar.indeterminateBar = document.createElement('div')
            bar.className = 'progressBar_progress indeterminate'
            ProgressBar.container.appendChild(bar);
        }
        return {
            disposed: false,
            [Symbol.dispose]() {
                if (this.disposed) return;
                if (--ProgressBar.indeterminateCtr === 0) {
                    ProgressBar.indeterminateBar.remove();
                }
                this.disposed = true;
            },
        };
    }
}
