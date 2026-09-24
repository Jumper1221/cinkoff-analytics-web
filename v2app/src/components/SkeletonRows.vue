<script setup lang="ts">
const props = withDefaults(defineProps<{ rows?: number; cols?: number }>(), { rows: 6, cols: 6 })
</script>
<template>
  <div v-for="r in props.rows" :key="r" class="skel-row" style="display: grid; gap: 18px;"
       :style="`grid-template-columns: repeat(${props.cols}, 1fr)`">
    <div v-for="c in (props.cols as number)" :key="c" class="skel" style="height: 16px;" />
  </div>
</template>
