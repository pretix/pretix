import vue from 'rollup-plugin-vue'
import { getBabelOutputPlugin } from '@rollup/plugin-babel'

export default {
  output: {
    format: 'iife',
    exports: 'named',
  },
  plugins: [
    getBabelOutputPlugin({
      presets: ['@babel/preset-env'],
      // Running babel on iife output is apparently discouraged since it can lead to global
      // variable leaks. Since we didn't get it to work on inputs, let's take that risk.
      // (In our tests, it did not leak anything.)
      allowAllFormats: true
    }),
    vue({
      css: true,
      compileTemplate: true,
      needMap: false,
    }),
  ],
};
