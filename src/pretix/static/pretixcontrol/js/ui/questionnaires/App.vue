<script setup lang="ts">
import Editor from './Editor.vue';
</script>

<template>
	<Suspense>
		<Editor/>
	</Suspense>
</template>
<style>
.progressBar { position: fixed; top: 0; left: 0; right: 0; z-index:1000000; pointer-events: none; }
.progressBar.local { position: absolute;  }
.progressBar .progressBar_progress { height: 5px; background: #0091EA; border-bottom: #026099; }
.progressBar .progressBar_progress.indeterminate {
    width: 30%; animation: slide 5s forwards;
}
.progressBarText { width: 100%; color: white; text-shadow: 1px 1px 1px black, -1px -1px 1px black;
    font-weight: bold; padding-left: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;  }
@keyframes slide {
    0% { width: 20%; }
    30% { width: 50%; }
    100% { width: 60%; }
}
</style>
