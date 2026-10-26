<template>
  <span class="brand-icon" :class="type" aria-hidden="true">
    <!-- Cursor -->
    <svg v-if="type === 'cursor'" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 3.2L4.5 8.6v6.8L12 20.8l7.5-5.4V8.6L12 3.2zm0 2.2l5.4 3.9v5.4L12 18.6l-5.4-3.9V9.3L12 5.4z"
        fill="#fff"
      />
      <path d="M12 8.2l2.8 2v3.6L12 15.8l-2.8-2V10.2L12 8.2z" fill="#111" />
    </svg>

    <!-- Codex / OpenAI-like -->
    <svg v-else-if="type === 'codex'" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 4.2c1.3 0 2.4.5 3.2 1.3l1.5-1.5A6.9 6.9 0 0012 2.2 6.9 6.9 0 005.2 6.8L6.8 8A4.8 4.8 0 0112 4.2zm6.8 2.6L17.2 8A4.8 4.8 0 0112 19.8c-1.3 0-2.4-.5-3.2-1.3L7.3 20a6.9 6.9 0 0011.5-5.4 6.9 6.9 0 00.0-7.8zM8.5 12a3.5 3.5 0 106.4 2l1.7 1.2A5.5 5.5 0 016.6 12c0-1.4.5-2.6 1.4-3.6L9.5 9.7A3.5 3.5 0 008.5 12z"
        fill="#fff"
      />
    </svg>

    <!-- Qoder -->
    <svg v-else-if="type === 'qoder'" viewBox="0 0 24 24" fill="none">
      <path d="M7 7h10v10H7V7zm2 2v6h6V9H9z" fill="#fff" />
      <path d="M14.5 14.5L18 18" stroke="#fff" stroke-width="2.2" stroke-linecap="round" />
    </svg>

    <span v-else class="fallback">+</span>
  </span>
</template>

<script setup>
defineProps({
  type: { type: String, default: 'custom' },
});
</script>

<style scoped>
.brand-icon {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
}
.brand-icon svg {
  width: 16px;
  height: 16px;
  display: block;
}
.brand-icon.cursor {
  background: #111111;
}
.brand-icon.codex {
  background: #111111;
  border-radius: 50%;
}
.brand-icon.qoder {
  background: linear-gradient(145deg, #12c26a, #0ea35a);
}
.brand-icon.custom {
  background: #718096;
}
.fallback {
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}
</style>
