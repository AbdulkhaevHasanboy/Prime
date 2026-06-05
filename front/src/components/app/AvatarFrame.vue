<script setup lang="ts">
/* Discord-style avatar decoration. The decoration SVG is painted BEHIND the
   avatar (drawn first), so themed parts — crown spikes, ears, wings — peek out
   around the round avatar while the inner parts tuck neatly behind it.
   Drop-in PNG art can replace these later via the `image` prop. */
type Variant = 'crown' | 'wings' | 'cat' | 'sparkle' | 'ring'

defineProps<{
  initials: string
  size: number
  variant?: Variant | null
  /* Optional PNG/SVG decoration (e.g. '/frames/crown.png') overlaid on top of
     the avatar. When set it overrides the built-in `variant` artwork. */
  image?: string
}>()

/* Rim colour per decoration tier. */
const RING_COLOR: Record<Variant, string> = {
  crown: '#f59e0b',
  wings: '#38bdf8',
  cat: '#a855f7',
  sparkle: '#6366f1',
  ring: '#94a3b8',
}
</script>

<template>
  <div
    class="relative inline-flex flex-shrink-0 items-center justify-center"
    :style="{ width: size + 'px', height: size + 'px' }"
  >
    <!-- Decoration (behind the avatar) -->
    <svg
      v-if="variant && !image"
      class="absolute inset-0 w-full h-full pointer-events-none"
      style="overflow: visible; transform: scale(1.45); transform-origin: 50% 44%; filter: drop-shadow(0 2px 3px rgba(15, 23, 42, 0.3))"
      viewBox="0 0 100 100"
      fill="none"
    >
      <!-- CROWN -->
      <template v-if="variant === 'crown'">
        <path
          d="M27 17 L21 -15 L40 4 L50 -23 L60 4 L79 -15 L73 17 Z"
          fill="#fbbf24"
          stroke="#b45309"
          stroke-width="2.4"
          stroke-linejoin="round"
        />
        <!-- bevel highlight along the left of each spike -->
        <path d="M27 17 L21 -15 L31 -5 Z M40 4 L50 -23 L52 -10 Z M60 4 L79 -15 L70 -4 Z" fill="#fde68a" opacity="0.7" />
        <rect x="27" y="13" width="46" height="11" rx="4" fill="#f59e0b" stroke="#b45309" stroke-width="2.2" />
        <rect x="31" y="15" width="38" height="2.6" rx="1.3" fill="#fde68a" opacity="0.85" />
        <circle cx="21" cy="-15" r="3.6" fill="#ef4444" stroke="#fff" stroke-width="1.2" />
        <circle cx="50" cy="-23" r="4.4" fill="#a855f7" stroke="#fff" stroke-width="1.2" />
        <circle cx="79" cy="-15" r="3.6" fill="#ef4444" stroke="#fff" stroke-width="1.2" />
        <circle cx="19.6" cy="-16.2" r="1" fill="#fff" opacity="0.9" />
        <circle cx="48.4" cy="-24.4" r="1.2" fill="#fff" opacity="0.9" />
      </template>

      <!-- ANGEL WINGS (two-tone for depth) -->
      <template v-else-if="variant === 'wings'">
        <g stroke-linejoin="round">
          <!-- base layer -->
          <path fill="#38bdf8" stroke="#0284c7" stroke-width="2" d="M84 58 C 100 58 113 53 124 44 C 116 48 109 48 103 48 C 119 45 130 38 137 26 C 126 32 117 33 110 34 C 125 28 134 18 138 6 C 123 19 106 35 93 47 C 89 51 86 54 84 58 Z" />
          <path fill="#38bdf8" stroke="#0284c7" stroke-width="2" transform="matrix(-1 0 0 1 100 0)" d="M84 58 C 100 58 113 53 124 44 C 116 48 109 48 103 48 C 119 45 130 38 137 26 C 126 32 117 33 110 34 C 125 28 134 18 138 6 C 123 19 106 35 93 47 C 89 51 86 54 84 58 Z" />
          <!-- light feather overlay -->
          <path fill="#e0f2fe" opacity="0.92" d="M90 51 C 102 49 111 45 119 38 C 112 41 106 42 101 42 C 113 38 122 32 127 23 C 119 28 111 30 105 31 C 116 26 122 19 124 11 C 113 22 99 36 90 45 Z" />
          <path fill="#e0f2fe" opacity="0.92" transform="matrix(-1 0 0 1 100 0)" d="M90 51 C 102 49 111 45 119 38 C 112 41 106 42 101 42 C 113 38 122 32 127 23 C 119 28 111 30 105 31 C 116 26 122 19 124 11 C 113 22 99 36 90 45 Z" />
        </g>
      </template>

      <!-- CAT EARS (rounded, with inner + highlight) -->
      <template v-else-if="variant === 'cat'">
        <path d="M23 13 C 16 -6 16 -18 24 -16 C 34 -13 44 0 47 6 C 39 11 29 13 23 13 Z" fill="#c084fc" stroke="#7e22ce" stroke-width="2.2" stroke-linejoin="round" />
        <path transform="matrix(-1 0 0 1 100 0)" d="M23 13 C 16 -6 16 -18 24 -16 C 34 -13 44 0 47 6 C 39 11 29 13 23 13 Z" fill="#c084fc" stroke="#7e22ce" stroke-width="2.2" stroke-linejoin="round" />
        <path d="M26 8 C 22 -3 22 -10 26 -9 C 31 -7 37 1 39 5 C 34 8 29 9 26 8 Z" fill="#f9a8d4" />
        <path transform="matrix(-1 0 0 1 100 0)" d="M26 8 C 22 -3 22 -10 26 -9 C 31 -7 37 1 39 5 C 34 8 29 9 26 8 Z" fill="#f9a8d4" />
      </template>

      <!-- SPARKLES (mid tier) -->
      <template v-else-if="variant === 'sparkle'">
        <g fill="#818cf8" stroke="#fff" stroke-width="1.2" stroke-linejoin="round">
          <path d="M73 -8 L77 1 L86 5 L77 9 L73 18 L69 9 L60 5 L69 1 Z" />
          <path d="M25 2 L27.2 6.8 L32 9 L27.2 11.2 L25 16 L22.8 11.2 L18 9 L22.8 6.8 Z" />
          <path d="M90 20 L91.6 23.4 L95 25 L91.6 26.6 L90 30 L88.4 26.6 L85 25 L88.4 23.4 Z" />
        </g>
        <circle cx="73" cy="5" r="1.4" fill="#fff" />
      </template>
    </svg>

    <!-- Avatar (on top, tucked slightly inside so the ring shows) -->
    <div
      class="absolute inset-[7%] rounded-full flex items-center justify-center font-display font-extrabold text-white bg-gradient-to-br from-indigo-500 to-violet-500"
      :style="{ fontSize: size * 0.32 + 'px' }"
    >
      {{ initials }}
    </div>

    <!-- Themed ring rim, painted over the avatar edge -->
    <svg
      v-if="variant && !image"
      class="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 100 100"
      fill="none"
    >
      <circle cx="50" cy="50" r="45" :stroke="RING_COLOR[variant]" stroke-width="5" />
    </svg>

    <!-- Drop-in PNG/SVG decoration art (overlaps the avatar, scaled out a bit) -->
    <img
      v-if="image"
      :src="image"
      alt=""
      class="absolute pointer-events-none select-none"
      style="inset: -22%; width: 144%; height: 144%; max-width: none"
    />
  </div>
</template>
