import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Bar } from '../api/client'

export const useReplayStore = defineStore('replay', () => {
  const code = ref('')
  const interval = ref('1d')
  const bars = ref<Bar[]>([])
  const currentIndex = ref(0)
  const isPlaying = ref(false)
  const speed = ref(4)
  const initialCapital = ref(100000)

  const visibleBars = computed(() => bars.value.slice(0, currentIndex.value + 1))
  const currentBar = computed(() => visibleBars.value[visibleBars.value.length - 1] || null)

  function setBars(newBars: Bar[]) {
    bars.value = newBars
    currentIndex.value = newBars.length - 1
  }

  function stepForward() {
    if (currentIndex.value < bars.value.length - 1) {
      currentIndex.value++
    }
  }

  function stepBack() {
    if (currentIndex.value > 0) {
      currentIndex.value--
    }
  }

  function reset() {
    currentIndex.value = 0
    isPlaying.value = false
  }

  return {
    code,
    interval,
    bars,
    currentIndex,
    isPlaying,
    speed,
    initialCapital,
    visibleBars,
    currentBar,
    setBars,
    stepForward,
    stepBack,
    reset,
  }
})
