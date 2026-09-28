// Safety net: capture Frappe's global __ (translate function) before any imports
// can overwrite it. Restored after mount if something downstream clobbered it.
const _frappe__ = typeof window !== 'undefined' && typeof window.__ === 'function' ? window.__ : null;

import { createApp, ref, h, defineComponent } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from './App.vue'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const routes = [
  { path: '/', name: 'list', component: () => import('./views/AutomationList.vue') },
  { path: '/builder/:name?', name: 'builder', component: () => import('./views/AutomationBuilder.vue') },
  { path: '/runs/:name', name: 'runs', component: () => import('./views/RunHistory.vue') },
  { path: '/templates', name: 'templates', component: () => import('./views/EmailTemplates.vue') },
  { path: '/variables', name: 'variables', component: () => import('./views/GlobalVariables.vue') },
]

const router = createRouter({
  history: createMemoryHistory('/'),
  routes,
})

const app = createApp(App)
app.use(router)

function mount() {
  const el = document.getElementById('automation-builder-app')
  if (el) {
    app.mount(el)
    // Restore Frappe's __ if it was clobbered during import/eval
    if (_frappe__ && typeof window.__ !== 'function') {
      window.__ = _frappe__
    }
  } else {
    setTimeout(mount, 100)
  }
}
mount()
