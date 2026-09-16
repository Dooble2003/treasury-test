import Papa from 'papaparse'
import type { Application, BeverageType, VerifyResponse } from './api'
import { STATUS_TEXT } from './status'

export const TEMPLATE_COLUMNS = [
  'reference',
  'label_files',
  'beverage_type',
  'brand_name',
  'class_type',
  'alcohol_content',
  'net_contents',
  'bottler',
  'country_of_origin',
]

export interface BatchRow {
  line: number
  reference: string
  labelFiles: string[]
  application: Application
}

export interface ParsedBatch {
  rows: BatchRow[]
  problems: string[]
}

const BEVERAGE_TYPES: Record<string, BeverageType> = {
  spirits: 'spirits',
  'distilled spirits': 'spirits',
  wine: 'wine',
  beer: 'beer',
  'malt beverage': 'beer',
}

export function templateCsv(): string {
  return Papa.unparse({
    fields: TEMPLATE_COLUMNS,
    data: [
      [
        'COLA-0001',
        'oldtom_front.jpg;oldtom_back.jpg',
        'spirits',
        'OLD TOM DISTILLERY',
        'Kentucky Straight Bourbon Whiskey',
        '45% Alc./Vol. (90 Proof)',
        '750 mL',
        'Old Tom Distillery, Bardstown, KY',
        '',
      ],
    ],
  })
}

export function parseBatchCsv(text: string): ParsedBatch {
  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: 'greedy',
    transformHeader: (header) =>
      header.trim().toLowerCase().replace(/\s+/g, '_'),
  })
  const columns = parsed.meta.fields ?? []
  if (!columns.includes('label_files')) {
    return {
      rows: [],
      problems: [
        'The spreadsheet needs a "label_files" column. Download the template to see the columns.',
      ],
    }
  }

  const rows: BatchRow[] = []
  const problems: string[] = []
  parsed.data.forEach((record, index) => {
    const line = index + 2
    const value = (key: string) => (record[key] ?? '').trim()
    const labelFiles = value('label_files')
      .split(/[;|]/)
      .map((name) => name.trim())
      .filter(Boolean)
    if (labelFiles.length === 0) {
      problems.push(`Row ${line}: no image file names in "label_files".`)
      return
    }
    const typeText = value('beverage_type').toLowerCase()
    const beverageType = typeText ? BEVERAGE_TYPES[typeText] : 'spirits'
    if (!beverageType) {
      problems.push(
        `Row ${line}: product type "${typeText}" should be spirits, wine or beer.`,
      )
      return
    }
    rows.push({
      line,
      reference: value('reference') || `Row ${line}`,
      labelFiles,
      application: {
        beverage_type: beverageType,
        brand_name: value('brand_name'),
        class_type: value('class_type'),
        alcohol_content: value('alcohol_content'),
        net_contents: value('net_contents'),
        bottler: value('bottler'),
        country_of_origin: value('country_of_origin'),
      },
    })
  })
  return { rows, problems }
}

export type RowState =
  | { status: 'waiting' }
  | { status: 'checking' }
  | { status: 'done'; result: VerifyResponse }
  | { status: 'error'; message: string }

export function resultsCsv(rows: BatchRow[], states: RowState[]): string {
  const fieldLabels = new Map<string, string>()
  states.forEach((state) => {
    if (state.status === 'done')
      state.result.fields.forEach((field) =>
        fieldLabels.set(field.key, field.label),
      )
  })

  const header = ['reference', 'label_files', 'result', 'message']
  fieldLabels.forEach((label) => header.push(label, `${label} note`))

  const data = rows.map((row, index) => {
    const state = states[index]
    const base = [row.reference, row.labelFiles.join(';')]
    if (state?.status === 'error') return [...base, 'Error', state.message]
    if (state?.status !== 'done') return [...base, 'Not checked', '']
    const byKey = new Map(
      state.result.fields.map((field) => [field.key, field]),
    )
    const cells = [
      ...base,
      STATUS_TEXT[state.result.overall],
      state.result.message,
    ]
    fieldLabels.forEach((_, key) => {
      const field = byKey.get(key)
      cells.push(field ? STATUS_TEXT[field.status] : '', field?.note ?? '')
    })
    return cells
  })
  return Papa.unparse({ fields: header, data })
}

export function downloadFile(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
