<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';

const viewport = ref<HTMLElement | null>(null);
const content = ref<HTMLElement | null>(null);
const scale = ref(1);
let observer: ResizeObserver | null = null;
let animationFrame: number | null = null;

function fitContent() {
  if (animationFrame !== null) cancelAnimationFrame(animationFrame);
  animationFrame = requestAnimationFrame(() => {
    if (!viewport.value || !content.value) return;
    if (viewport.value.clientWidth === 0 || viewport.value.clientHeight === 0) return;
    const widthScale = viewport.value.clientWidth / content.value.scrollWidth;
    const heightScale = viewport.value.clientHeight / content.value.scrollHeight;
    scale.value = Math.min(1, widthScale, heightScale);
  });
}

onMounted(() => {
  observer = new ResizeObserver(fitContent);
  if (viewport.value) observer.observe(viewport.value);
  if (content.value) observer.observe(content.value);
  void nextTick(fitContent);
});

onBeforeUnmount(() => {
  observer?.disconnect();
  if (animationFrame !== null) cancelAnimationFrame(animationFrame);
});
</script>

<template>
  <div ref="viewport" class="display-fit">
    <div ref="content" class="display-fit__content" :style="{ transform: `scale(${scale})` }">
      <slot />
    </div>
  </div>
</template>
