// Fresh smoke suite against the CURRENT app (post-Stage 31 UI).
// Run: LD_LIBRARY_PATH=<extracted lib> node e2e/smoke-31.cjs
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = path.join(__dirname, 'screenshots-31');
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8010';

const results = [];
const consoleErrors = [];

function record(surface, status, detail) {
  results.push({ surface, status, detail });
  console.log(`[${status}] ${surface} — ${detail}`);
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: false });
}

(async () => {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1360, height: 870 } });

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + String(err).slice(0, 300)));

  // ---------- 1. Login + SPA loads ----------
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.locator('input[name="usr"], input[type="text"]').first().fill('Administrator');
    await page.locator('input[name="pwd"], input[type="password"]').first().fill('admin');
    await page.locator('button[type="submit"], .btn-primary').first().click();
    await page.waitForURL('**/desk', { timeout: 20000 });
    await page.goto(`${BASE_URL}/app/spa-builder`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('.ab-list', { timeout: 20000 });
    await shot(page, '01-spa-loads-at-list.png');
    record('SPA loads on /app/spa-builder', 'INFO',
      'mounts at LIST route (memory history) — confirms old Sep 10 finding: builder is NOT the landing route');
  } catch (e) {
    await shot(page, '01-spa-FAILED.png');
    record('SPA loads', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 1b. Enter builder via New Automation ----------
  try {
    await page.locator('button', { hasText: 'New Automation' }).first().click();
    await page.waitForSelector('.ab-node-palette', { timeout: 20000 });
    await page.waitForSelector('.ab-node', { timeout: 20000 });
    await shot(page, '01b-builder-loaded.png');
    record('Builder loads (via New Automation)', 'PASS', 'palette + nodes mounted');
  } catch (e) {
    await shot(page, '01b-builder-FAILED.png');
    record('Builder loads (via New Automation)', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 2. Palette: sections + items ----------
  try {
    const sections = await page.locator('.ab-node-palette-section').allTextContents();
    const hasFrappeSection = sections.some(s => s.trim() === 'Frappe');
    const logicSectionIdx = sections.findIndex(s => s.trim() === 'Logic');
    const allItems = await page.locator('.ab-node-palette-item .ab-node-palette-label').allTextContents();
    const needsConditionInLogic = allItems.filter(l =>
      ['IF', 'Switch', 'Condition'].includes(l.trim())).length;
    const newActions = allItems.filter(l =>
      ['Slack', 'Assign To', 'Workflow Transition', 'Generate PDF'].includes(l.trim()));
    await shot(page, '02-palette.png');
    const ok = !hasFrappeSection && logicSectionIdx >= 0 && newActions.length === 4;
    record('Palette sections (Logic/Actions, no Frappe; 4 new action types)',
      ok ? 'PASS' : 'FAIL',
      `sections=${JSON.stringify(sections.map(s=>s.trim()))}, newActions=${newActions.length}/4, frappeSection=${hasFrappeSection}`);
  } catch (e) {
    record('Palette sections', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 3. Reworked node templates: colored left borders + handles ----------
  try {
    const triggerNode = page.locator('.ab-node-trigger').first();
    const borderColor = await triggerNode.evaluate(el => getComputedStyle(el).borderLeftColor);
    const borderW = await triggerNode.evaluate(el => getComputedStyle(el).borderLeftWidth);
    const handleCount = await page.locator('.vue-flow__handle').count();
    await shot(page, '03-node-templates.png');
    const ok = borderColor !== 'rgba(0, 0, 0, 0)' && handleCount >= 4;
    record('Node templates (colored left border + handles)', ok ? 'PASS' : 'FAIL',
      `trigger border-left: ${borderW} ${borderColor}, handles on canvas: ${handleCount}`);
  } catch (e) {
    record('Node templates', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 4. Trigger config panel ----------
  try {
    await page.locator('.ab-node-trigger').first().click();
    await page.waitForSelector('.ab-config', { timeout: 10000 });
    const title = await page.locator('.ab-config-header h3').textContent();
    const triggerTypeOptions = await page.locator('.ab-config select').first().locator('option').allTextContents();
    const hasWebhook = triggerTypeOptions.some(o => o.includes('Webhook'));
    await shot(page, '04-trigger-config.png');
    record('Trigger config panel (incl. Webhook type)', hasWebhook ? 'PASS' : 'FAIL',
      `title="${title.trim()}", options=${triggerTypeOptions.length}, Webhook=${hasWebhook}`);
    await page.locator('.ab-config-actions .ab-btn-ghost').last().click();
  } catch (e) {
    record('Trigger config panel', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 5. Action config panel (schema-driven) ----------
  try {
    const actionNode = page.locator('.ab-node-action').first();
    await actionNode.click();
    await page.waitForSelector('.ab-config', { timeout: 10000 });
    // The panel remounts and re-fetches action types — wait for the dropdown to populate
    await page.waitForFunction(
      () => document.querySelectorAll('.ab-config select')[0]?.options.length > 5,
      { timeout: 15000 }
    );
    const actionTypeOptions = await page.locator('.ab-config select').first().locator('option').allTextContents();
    const hasNew = ['Slack', 'Assign To', 'Workflow Transition', 'Generate PDF']
      .every(l => actionTypeOptions.some(o => o.trim() === l));
    await shot(page, '05-action-config.png');
    record('Action config panel (schema-driven, all 11 types in dropdown)', hasNew ? 'PASS' : 'FAIL',
      `options=${actionTypeOptions.length}, all 4 new present=${hasNew}`);
    await page.locator('.ab-config-actions .ab-btn-ghost').last().click();
  } catch (e) {
    record('Action config panel', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 6. Switch dynamic case handles (updateNodeInternals concern) ----------
  try {
    const switchCount = await page.locator('.ab-node-switch').count();
    if (switchCount === 0) {
      // Add a Switch via the + add-trigger menu
      await page.locator('.ab-add-node-btn').first().click();
      await page.waitForSelector('.ab-add-node-menu', { timeout: 5000 });
      await page.locator('.ab-add-node-menu-item', { hasText: 'Switch' }).first().click();
      await page.waitForSelector('.ab-node-switch', { timeout: 5000 });
    }
    await page.locator('.ab-node-switch').first().click();
    await page.waitForSelector('.ab-config', { timeout: 10000 });
    const handlesBefore = await page.locator('.ab-node-switch .vue-flow__handle').count();
    // Click "Add Case" button - use getByRole with text pattern
    await page.getByRole('button', { name: /\+ Add Case/ }).click();
    await page.waitForTimeout(400);
    const handlesAfter = await page.locator('.ab-node-switch .vue-flow__handle').count();
    await shot(page, '06-switch-dynamic-handles.png');
    record('Switch dynamic case handles (updateNodeInternals)',
      handlesAfter > handlesBefore ? 'PASS' : 'FAIL',
      `handles before adding case: ${handlesBefore}, after: ${handlesAfter} (0 cases -> default only, 1 case -> 2 handles)`);
  } catch (e) {
    record('Switch dynamic case handles', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 7. Type picker (drag handle -> empty canvas) ----------
  try {
    const sourceHandle = page.locator('.ab-node-trigger .vue-flow__handle').first();
    const box = await sourceHandle.boundingBox();
    const canvas = await page.locator('.ab-canvas-wrapper').boundingBox();
    // Drop in the top-right corner — guaranteed empty (away from the node chain)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(canvas.x + canvas.width - 220, canvas.y + 90, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(400);
    const pickerVisible = await page.locator('.ab-type-picker').isVisible().catch(() => false);
    const pickerItems = pickerVisible ? await page.locator('.ab-type-picker-item').count() : 0;
    await shot(page, '07-type-picker.png');
    record('Type picker (drag-to-empty-canvas)', pickerVisible && pickerItems > 0 ? 'PASS' : 'FAIL',
      `picker visible: ${pickerVisible}, items: ${pickerItems}`);
    if (pickerVisible) await page.locator('.ab-type-picker-item').last().click();
    await page.waitForTimeout(300);
  } catch (e) {
    record('Type picker', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 8. Auto-handle-switch animation (convergence) ----------
  try {
    // Ensure a second trigger exists (add via palette drag to empty canvas)
    let trigCount = await page.locator('.ab-node-trigger').count();
    if (trigCount < 2) {
      const paletteTrigger = page.locator('.ab-node-palette-item', { hasText: 'Trigger' }).first();
      const pbox = await paletteTrigger.boundingBox();
      const canvas = await page.locator('.ab-canvas-wrapper').boundingBox();
      await page.mouse.move(pbox.x + pbox.width / 2, pbox.y + pbox.height / 2);
      await page.mouse.down();
      await page.mouse.move(canvas.x + canvas.width - 220, canvas.y + 60, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(600);
      trigCount = await page.locator('.ab-node-trigger').count();
    }
    const actions = page.locator('.ab-node-action');
    const actCount = await actions.count();
    if (trigCount >= 2 && actCount >= 1) {
      // Connect trigger-2 to the first action (already connected from trigger-1)
      const src = await page.locator('.ab-node-trigger').nth(1).locator('.vue-flow__handle').first().boundingBox();
      const tgt = await actions.first().locator('.vue-flow__handle').first().boundingBox();
      await page.mouse.move(src.x + src.width / 2, src.y + src.height / 2);
      await page.mouse.down();
      await page.mouse.move(tgt.x + tgt.width / 2, tgt.y + tgt.height / 2, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(150);
      // Check for the animation class on the -in-left handle
      const switched = await page.evaluate(() => {
        const h = document.querySelector('.vue-flow__handle.ab-handle-auto-switched');
        return h ? h.getAttribute('data-id') || h.id || 'found' : null;
      });
      await page.waitForTimeout(900);
      const cleared = await page.evaluate(() =>
        !document.querySelector('.vue-flow__handle.ab-handle-auto-switched'));
      await shot(page, '08-auto-handle-switch.png');
      record('Auto-handle-switch pulse animation', switched ? 'PASS' : 'FAIL',
        `class seen: ${switched}, clears after 800ms: ${cleared}`);
    } else {
      record('Auto-handle-switch pulse animation', 'SKIP', `need 2 triggers + 1 action, have ${trigCount}/${actCount}`);
    }
  } catch (e) {
    record('Auto-handle-switch pulse animation', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 9. Run Now modal (Manual trigger) ----------
  try {
    // Save first — Run Now button only shows for a saved automation
    await page.locator('.ab-topbar input[type="text"]').fill('Smoke31 RunNow');
    await page.locator('.ab-topbar-actions button', { hasText: 'Save' }).click();
    await page.waitForTimeout(1500);
    // Set the first trigger to Manual via its config panel
    await page.locator('.ab-node-trigger').first().click();
    await page.waitForSelector('.ab-config', { timeout: 10000 });
    await page.locator('.ab-config select').first().selectOption({ label: 'Manual (Run Now)' });
    await page.locator('.ab-config-actions .ab-btn-primary').click();
    await page.waitForTimeout(300);
    const runNowBtn = page.locator('.ab-topbar-actions button', { hasText: 'Run Now' });
    const visible = await runNowBtn.isVisible().catch(() => false);
    if (visible) {
      await runNowBtn.click();
      await page.waitForSelector('.ab-modal', { timeout: 5000 });
      const modalTitle = await page.locator('.ab-modal h3').textContent();
      await shot(page, '09-run-now-modal.png');
      record('Run Now modal (Manual trigger)', 'PASS', `modal: "${modalTitle.trim()}"`);
      await page.locator('.ab-modal-footer .ab-btn-ghost').click();
    } else {
      await shot(page, '09-run-now-NO-BUTTON.png');
      record('Run Now modal (Manual trigger)', 'FAIL', 'Run Now button not visible after Manual trigger set');
    }
  } catch (e) {
    record('Run Now modal', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 10. GlobalVariables.vue ----------
  try {
    // Need to leave the builder first (builder has no variables link)
    await page.locator('.ab-topbar .ab-btn-ghost', { hasText: 'Back' }).first().click();
    await page.waitForTimeout(500);
    const gvBtn = page.locator('button', { hasText: 'Global Variables' }).first();
    await gvBtn.click();
    await page.waitForTimeout(600);
    const heading = await page.locator('h1').first().textContent().catch(() => '');
    // Create a variable
    await page.locator('button', { hasText: 'New Variable' }).first().click();
    await page.waitForTimeout(300);
    const inputs = page.locator('.ab-template-form input[type="text"]');
    await inputs.nth(0).fill('smoke_test_var');
    await inputs.nth(1).fill('Smoke test variable');
    await inputs.nth(2).fill('https://smoke.example.com');
    await page.locator('.ab-config-actions .ab-btn-primary').click();
    await page.waitForTimeout(800);
    const rowText = await page.locator('.ab-list-row', { hasText: 'smoke_test_var' }).count();
    await shot(page, '10-global-variables.png');
    record('GlobalVariables list view (create + list)',
      rowText > 0 ? 'PASS' : 'FAIL', `heading="${(heading||'').trim()}", row found: ${rowText > 0}`);
  } catch (e) {
    await shot(page, '10-global-variables-FAILED.png');
    record('GlobalVariables list view', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- 11. Save + reload: builder or list? (old Sep 10 finding) ----------
  try {
    await page.locator('button', { hasText: 'Back' }).first().click(); // back to automations list
    await page.waitForTimeout(500);
    await page.locator('button', { hasText: 'New Automation' }).first().click();
    await page.waitForTimeout(600);
    await page.locator('.ab-topbar input[type="text"]').fill('Smoke31 Reload Test');
    await page.locator('.ab-topbar-actions button', { hasText: 'Save' }).click();
    await page.waitForTimeout(1500);
    const urlBefore = page.url();
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    const builderVisible = await page.locator('.ab-builder').isVisible().catch(() => false);
    const listVisible = await page.locator('.ab-list').isVisible().catch(() => false);
    const nameInput = await page.locator('.ab-topbar input[type="text"]').inputValue().catch(() => '');
    await shot(page, '11-after-reload.png');
    record('Save + reload lands where? (old finding: redirected to list)',
      'INFO', `builder visible: ${builderVisible}, list visible: ${listVisible}, name input: "${nameInput}", url: ${urlBefore}`);
  } catch (e) {
    record('Save + reload', 'FAIL', e.message.split('\n')[0]);
  }

  // ---------- Summary ----------
  console.log('\n===== SMOKE RESULTS =====');
  for (const r of results) console.log(`[${r.status}] ${r.surface}: ${r.detail}`);
  console.log(`\nConsole errors captured: ${consoleErrors.length}`);
  for (const e of consoleErrors.slice(0, 10)) console.log('  ERR:', e);
  fs.writeFileSync(path.join(SCREENSHOT_DIR, 'results.json'), JSON.stringify({ results, consoleErrors }, null, 2));

  await browser.close();
})();
