<template>
  <div class="ab-templates">
    <div class="ab-list-header">
      <h1>Global Variables</h1>
      <div style="display: flex; gap: 8px;">
        <button class="ab-btn ab-btn-ghost ab-btn-sm" @click="goBack">← Back</button>
        <button class="ab-btn ab-btn-primary ab-btn-sm" @click="createNew">New Variable</button>
      </div>
    </div>

    <div v-if="loading" class="ab-loading">Loading...</div>

    <div v-else-if="variables.length === 0 && !editing" class="ab-empty">
      <p>No global variables yet. Create one to reference as <code v-pre>{{env.varname}}</code> in any action.</p>
    </div>

    <!-- Edit form -->
    <div v-if="editing" class="ab-template-form">
      <div class="ab-config-group">
        <label>Variable Name</label>
        <input type="text" v-model="form.variable_name" placeholder="e.g. default_sender_email" />
      </div>
      <div class="ab-config-group">
        <label>Description</label>
        <input type="text" v-model="form.description" placeholder="What is this variable for?" />
      </div>
      <div class="ab-config-group">
        <label>Value</label>
        <input type="text" v-model="form.value" placeholder="e.g. notifications@example.com" />
      </div>
      <p class="ab-config-hint">Use <code v-pre>{{env.variable_name}}</code> in action configs to resolve this value.</p>
      <div class="ab-config-actions">
        <button class="ab-btn ab-btn-primary" @click="saveVariable" :disabled="saving">
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
        <button class="ab-btn ab-btn-ghost" @click="cancelEdit">Cancel</button>
      </div>
    </div>

    <!-- List -->
    <div v-else>
      <div v-for="v in variables" :key="v.name" class="ab-list-row" @click="editVariable(v)">
        <div class="ab-list-row-left">
          <div class="ab-list-row-subject">
            <span class="ab-list-row-title">{{ v.variable_name }}</span>
          </div>
          <div class="ab-list-row-meta">{{ v.description || v.value }}</div>
        </div>
        <div class="ab-list-row-right">
          <div class="ab-row-actions">
            <button class="ab-row-action-btn" @click.stop="editVariable(v)">Edit</button>
            <button class="ab-row-action-btn ab-row-action-btn--danger" @click.stop="deleteVariable(v)">Delete</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listGlobalVariables, saveGlobalVariable } from '../composables/api.js'

const router = useRouter()
const variables = ref([])
const loading = ref(true)
const editing = ref(false)
const saving = ref(false)
const form = ref({ variable_name: '', description: '', value: '' })
const editingName = ref(null)

async function load() {
  try {
    variables.value = await listGlobalVariables()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function createNew() {
  form.value = { variable_name: '', description: '', value: '' }
  editingName.value = null
  editing.value = true
}

function editVariable(v) {
  form.value = { variable_name: v.variable_name, description: v.description || '', value: v.value || '' }
  editingName.value = v.name
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editingName.value = null
  form.value = { variable_name: '', description: '', value: '' }
}

async function saveVariable() {
  if (!form.value.variable_name.trim()) {
    frappe.msgprint('Please enter a variable name')
    return
  }
  saving.value = true
  try {
    await saveGlobalVariable({
      name: editingName.value,
      variable_name: form.value.variable_name.trim(),
      description: form.value.description,
      value: form.value.value,
    })
    frappe.show_alert({ message: 'Variable saved', indicator: 'green' })
    editing.value = false
    await load()
  } catch (e) {
    frappe.msgprint('Save failed: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

async function deleteVariable(v) {
  if (!confirm(`Delete variable "${v.variable_name}"?`)) return
  try {
    await frappe.call({
      method: 'frappe.client.delete',
      args: { doctype: 'Automation Global Variable', name: v.name },
    })
    frappe.show_alert({ message: 'Variable deleted', indicator: 'green' })
    await load()
  } catch (e) {
    frappe.msgprint('Delete failed: ' + (e.message || e))
  }
}

function goBack() {
  router.push({ name: 'list' })
}

onMounted(load)
</script>
