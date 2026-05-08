/* eslint-disable */
/**
 * Evolution: Replay failed Meta Automation tasks
 *
 * Uses WorkboardHelper.handleUpdateMetaAutomation directly.
 *   - CSV mode  → parse CSV, format into WorkboardTaskModel shape, pass to handleUpdateMetaAutomation
 *   - DB mode   → fetch real WorkboardTaskModel from DB, pass directly to handleUpdateMetaAutomation
 *
 * Prerequisites:
 *   npm install @napi-rs/snappy-darwin-arm64 --no-save   (fixes mongoose native binding)
 *
 * Usage:
 *   npm run build
 *   node dist/evolutions/replayMetaAutomationTasks.js [--dry-run]
 */

import * as path from 'path';
import * as fs from 'fs';
import csv2json from 'csvtojson';
import { createObjectCsvWriter } from 'csv-writer';

// ── Project imports (initialises DB + Sequelize on load) ─────────────────────
import DB from '@/databases';
import WorkboardHelper from '@/helpers/workboard.helper';
import { WorkboardTaskModel } from '@/models/workboardTasks.model';
import { IUpdateMetaAutomationCustomFields } from '@/typings/workboard';

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  /** 'csv' = read from file, 'db' = query workboard_tasks table */
  dataSource: 'csv' as 'csv' | 'db',

  /** CSV/XLSX path (used when dataSource = 'csv') */
  csvPath: path.join(process.env.HOME!, 'Downloads/api_errors_classified.csv'),

  /** Specific task IDs to replay from DB (empty = all failed meta_automation tasks) */
  taskIds: [] as number[],

  /** Delay between API calls (ms) — avoids Meta rate limiting */
  delayMs: 500,

  /** Dry run — logs custom_fields without calling API */
  dryRun: process.argv.includes('--dry-run'),

  /** Only replay tasks with these error_classification values (empty = all) */
  retryClassifications: [] as string[],

  /** Output CSV path for results */
  outputCsv: path.join(process.env.HOME!, 'Downloads/meta_replay_results.csv'),
};

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface CsvRow {
  id: string | number;
  seller_id: string;
  assignee: string;
  sub_type: string;
  status: string;
  meta_entity_type: string;
  meta_id: string;
  ad_account_id: string;
  budget_level?: string;
  budget_type?: string;
  budget_amount?: string | number;
  extra_custom_fields?: string;
  error_classification?: string;
}

interface ResultRow {
  task_id: string | number;
  seller_id: string;
  meta_entity_type: string;
  meta_id: string;
  ad_account_id: string;
  status: 'success' | 'failed' | 'skipped' | 'dry_run';
  error_classification: string;
  error_message: string;
  custom_fields: string;
  response?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DATA SOURCE: CSV → format into WorkboardTaskModel shape
// ═══════════════════════════════════════════════════════════════════════════════

function parseExtra(raw?: string): Partial<IUpdateMetaAutomationCustomFields> {
  if (!raw) return {};
  try {
    let parsed: unknown = JSON.parse(raw);
    // CSV/XLSX may double-serialize: first parse yields a string
    if (typeof parsed === 'string') parsed = JSON.parse(parsed);
    return (parsed ?? {}) as Partial<IUpdateMetaAutomationCustomFields>;
  } catch {
    return {};
  }
}

/**
 * CSV mode: parse row → build custom_fields → cast as WorkboardTaskModel
 */
function csvRowToTask(row: CsvRow): WorkboardTaskModel {
  const extra = parseExtra(row.extra_custom_fields);

  const custom_fields: IUpdateMetaAutomationCustomFields = {
    // Direct columns from CSV
    ad_account_id: row.ad_account_id,
    meta_entity_type: row.meta_entity_type,
    meta_id: String(row.meta_id),
    ...(row.budget_level && { budget_level: row.budget_level }),
    ...(row.budget_type && { budget_type: row.budget_type }),
    ...(row.budget_amount !== undefined && row.budget_amount !== '' && { budget_amount: Number(row.budget_amount) }),
    // Parsed extra_custom_fields (publisher_platforms, age, gender, geo, etc.)
    ...extra,
  };

  return {
    id: Number(row.id),
    seller_id: row.seller_id,
    assignee: row.assignee,
    sub_type: row.sub_type,
    status: row.status,
    custom_fields,
  } as unknown as WorkboardTaskModel;
}

async function fetchFromCsv(filePath: string): Promise<{ tasks: WorkboardTaskModel[]; csvRows: CsvRow[] }> {
  let csvRows: CsvRow[];
  if (filePath.endsWith('.xlsx')) {
    const XLSX = require('xlsx');
    const wb = XLSX.readFile(filePath);
    csvRows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' });
  } else {
    csvRows = await csv2json().fromFile(filePath);
  }
  const tasks = csvRows.map(csvRowToTask);
  return { tasks, csvRows };
}

// ═══════════════════════════════════════════════════════════════════════════════
// DATA SOURCE: DB → fetch real WorkboardTaskModel, pass directly
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchFromDb(taskIds: number[]): Promise<{ tasks: WorkboardTaskModel[]; csvRows: CsvRow[] }> {
  const where: any = {
    type: 'meta_automation',
    trigger_status: 'failed',
  };
  if (taskIds.length) where.id = taskIds;

  const tasks = await DB.WorkboardTask.findAll({ where, order: [['id', 'ASC']] });

  // Build csvRows for result CSV / error_classification (not available from DB, leave empty)
  const csvRows: CsvRow[] = tasks.map(t => {
    const cf = (t.custom_fields || {}) as IUpdateMetaAutomationCustomFields;
    return {
      id: t.id,
      seller_id: t.seller_id,
      assignee: t.assignee,
      sub_type: t.sub_type,
      status: t.status,
      meta_entity_type: cf.meta_entity_type || '',
      meta_id: cf.meta_id || '',
      ad_account_id: cf.ad_account_id || '',
      error_classification: '',
    };
  });

  return { tasks, csvRows };
}

// ═══════════════════════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════════════════════

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

function extractErrorMsg(err: unknown): string {
  if (!err) return 'Unknown error';
  // handleUpdateMetaAutomation throws the API response object on failure
  if (typeof err === 'object' && err !== null) {
    const obj = err as any;
    if (obj.error_message) return String(obj.error_message);
    // Try nested response.error.error_user_msg
    const str = JSON.stringify(err);
    const match = str.match(/error_user_msg["\s:]+([^"]+)/);
    if (match) return match[1];
    return str.substring(0, 200);
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

async function main(): Promise<void> {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('  Meta Automation Task Replay');
  console.log(`  Source : ${CONFIG.dataSource}`);
  console.log(`  Dry run: ${CONFIG.dryRun}`);
  console.log(`  Delay  : ${CONFIG.delayMs}ms`);
  console.log('═══════════════════════════════════════════════════════════\n');

  // ── 1. Fetch tasks ─────────────────────────────────────────────────────────

  let tasks: WorkboardTaskModel[];
  let csvRows: CsvRow[];

  if (CONFIG.dataSource === 'db') {
    console.log('Querying workboard_tasks (type=meta_automation, trigger_status=failed)...');
    ({ tasks, csvRows } = await fetchFromDb(CONFIG.taskIds));
  } else {
    if (!fs.existsSync(CONFIG.csvPath)) {
      console.error(`File not found: ${CONFIG.csvPath}`);
      process.exit(1);
    }
    console.log(`Reading: ${path.basename(CONFIG.csvPath)}`);
    ({ tasks, csvRows } = await fetchFromCsv(CONFIG.csvPath));
  }
  console.log(`Loaded ${tasks.length} tasks`);

  // ── 2. Filter by error classification (CSV only, DB rows have no classification) ──

  let indices: number[] = Array.from({ length: tasks.length }, (_, i) => i);
  if (CONFIG.retryClassifications.length && CONFIG.dataSource === 'csv') {
    indices = indices.filter(i => CONFIG.retryClassifications.includes(csvRows[i].error_classification ?? ''));
    console.log(`Filtered → ${indices.length} tasks (${CONFIG.retryClassifications.join(', ')})`);
  }
  console.log();

  // ── 3. Process ─────────────────────────────────────────────────────────────

  const workboardHelper = new WorkboardHelper();
  const results: ResultRow[] = [];
  const errorBuckets: Record<string, { count: number; sample: string }> = {};
  let successCount = 0, failedCount = 0, skippedCount = 0;

  for (let idx = 0; idx < indices.length; idx++) {
    const i = indices[idx];
    const task = tasks[i];
    const row = csvRows[i];
    const taskId = task.id ?? row.id;
    const cf = (task.custom_fields || {}) as Partial<IUpdateMetaAutomationCustomFields>;

    const metaEntityType = cf.meta_entity_type || row.meta_entity_type || '';
    const metaId = cf.meta_id || row.meta_id || '';
    const adAccountId = cf.ad_account_id || row.ad_account_id || '';

    // Skip rows with missing required fields
    if (!metaId || !adAccountId || !metaEntityType) {
      console.log(`[${idx + 1}/${indices.length}] task ${taskId} — SKIP (missing required fields)`);
      results.push({
        task_id: taskId, seller_id: row.seller_id, meta_entity_type: metaEntityType,
        meta_id: metaId, ad_account_id: adAccountId, status: 'skipped',
        error_classification: row.error_classification || '',
        error_message: 'Missing meta_id / ad_account_id / meta_entity_type', custom_fields: '',
      });
      skippedCount++;
      continue;
    }

    console.log(
      `[${idx + 1}/${indices.length}] task ${taskId} | ${metaEntityType} | entity: ${metaId} | prev_error: ${row.error_classification || '-'}`,
    );

    // Dry run — log and skip
    if (CONFIG.dryRun) {
      console.log('  → [DRY RUN] custom_fields:', JSON.stringify(cf, null, 2));
      results.push({
        task_id: taskId, seller_id: row.seller_id, meta_entity_type: metaEntityType,
        meta_id: metaId, ad_account_id: adAccountId, status: 'dry_run',
        error_classification: row.error_classification || '', error_message: '',
        custom_fields: JSON.stringify(cf),
      });
      successCount++;
      continue;
    }

    // ── Call handleUpdateMetaAutomation ─────────────────────────────────────
    try {
      const res = await workboardHelper.handleUpdateMetaAutomation(task);

      results.push({
        task_id: taskId, seller_id: row.seller_id, meta_entity_type: metaEntityType,
        meta_id: metaId, ad_account_id: adAccountId, status: 'success',
        error_classification: '', error_message: '', custom_fields: JSON.stringify(cf),
        response: JSON.stringify(res),
      });
    
      successCount++;
    } catch (err) {
      const errMsg = extractErrorMsg(err);
      const classification = row.error_classification || 'Unknown';
      console.log(`  ✗ failed  | ${errMsg}`);

      if (!errorBuckets[classification]) errorBuckets[classification] = { count: 0, sample: errMsg };
      errorBuckets[classification].count++;

      results.push({
        task_id: taskId, seller_id: row.seller_id, meta_entity_type: metaEntityType,
        meta_id: metaId, ad_account_id: adAccountId, status: 'failed',
        error_classification: classification, error_message: errMsg, custom_fields: JSON.stringify(cf),
        response: JSON.stringify(err),
      });
      failedCount++;
    }

    await sleep(CONFIG.delayMs);
  }

  // ── 4. Write result CSV ────────────────────────────────────────────────────

  const csvWriter = createObjectCsvWriter({
    path: CONFIG.outputCsv,
    header: [
      { id: 'task_id', title: 'task_id' },
      { id: 'seller_id', title: 'seller_id' },
      { id: 'meta_entity_type', title: 'meta_entity_type' },
      { id: 'meta_id', title: 'meta_id' },
      { id: 'ad_account_id', title: 'ad_account_id' },
      { id: 'status', title: 'status' },
      { id: 'error_classification', title: 'error_classification' },
      { id: 'error_message', title: 'error_message' },
      { id: 'custom_fields', title: 'custom_fields' },
      { id: 'response', title: 'response' },
    ],
  });
  await csvWriter.writeRecords(results);
  console.log(`\nResults → ${CONFIG.outputCsv}`);

  // ── 5. Summary ─────────────────────────────────────────────────────────────

  console.log('\n═══ Summary ═══════════════════════════════════════════════');
  console.log(`  Total   : ${indices.length}`);
  console.log(`  Success : ${successCount}`);
  console.log(`  Failed  : ${failedCount}`);
  console.log(`  Skipped : ${skippedCount}`);

  if (Object.keys(errorBuckets).length) {
    console.log('\n═══ Unique Errors ═════════════════════════════════════════');
    const sorted = Object.entries(errorBuckets).sort((a, b) => b[1].count - a[1].count);
    for (const [classification, { count, sample }] of sorted) {
      console.log(`  [${count}x] ${classification}`);
      console.log(`        ${sample.substring(0, 120)}`);
    }
  }

  console.log('═══════════════════════════════════════════════════════════');
  process.exit(0);
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
