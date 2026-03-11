import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', {
  state: () => ({
    sideOpen: true,
  }),
  actions: {
    toggleSidebar(): void {
      this.sideOpen = !this.sideOpen
    },
  },
})
