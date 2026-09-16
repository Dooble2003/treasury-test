import { Fragment, useEffect, useId, useMemo, useRef, useState } from 'react'
import { verifyLabel } from '../api'
import {
  downloadFile,
  parseBatchCsv,
  resultsCsv,
  templateCsv,
  type ParsedBatch,
  type RowState,
} from '../batch'
import Results from '../components/Results'
import StatusBadge from '../components/StatusBadge'
import { ACCEPTED_TYPES, fetchSample, prepareImage } from '../images'

// The server checks one label at a time; a few in flight keeps uploads ahead of it.
const CONCURRENT_REQUESTS = 3

type Filter = 'all' | 'fail' | 'review' | 'pass' | 'error'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'fail', label: 'Does not match' },
  { value: 'review', label: 'Needs a closer look' },
  { value: 'pass', label: 'Matches' },
  { value: 'error', label: 'Could not check' },
]

function rowCategory(state: RowState | undefined): Filter | null {
  if (!state || state.status === 'waiting' || state.status === 'checking')
    return null
  if (state.status === 'error' || state.result.overall === 'unreadable')
    return 'error'
  return state.result.overall
}

export default function BatchCheck() {
  const id = useId()
  const [csvName, setCsvName] = useState('')
  const [batch, setBatch] = useState<ParsedBatch | null>(null)
  const [images, setImages] = useState<Map<string, File>>(new Map())
  const [states, setStates] = useState<RowState[]>([])
  const [running, setRunning] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')
  const [openRow, setOpenRow] = useState<number | null>(null)
  const controller = useRef<AbortController | null>(null)

  const rows = useMemo(() => batch?.rows ?? [], [batch])
  const missingByRow = useMemo(
    () =>
      rows.map((row) =>
        row.labelFiles.filter((name) => !images.has(name.toLowerCase())),
      ),
    [rows, images],
  )
  const readyCount = missingByRow.filter(
    (missing) => missing.length === 0,
  ).length
  const missingNames = [...new Set(missingByRow.flat())]
  const finished = states.filter(
    (s) => s.status === 'done' || s.status === 'error',
  ).length

  useEffect(() => {
    if (!running) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [running])

  function loadCsv(name: string, text: string) {
    setCsvName(name)
    setBatch(parseBatchCsv(text))
    setStates([])
    setOpenRow(null)
  }

  function addImages(list: FileList | File[]) {
    setImages((current) => {
      const next = new Map(current)
      Array.from(list)
        .filter(
          (file) => ACCEPTED_TYPES.includes(file.type) || file.type === '',
        )
        .forEach((file) => next.set(file.name.toLowerCase(), file))
      return next
    })
  }

  function updateRow(index: number, state: RowState) {
    setStates((current) => {
      const next = [...current]
      next[index] = state
      return next
    })
  }

  async function start() {
    const abort = new AbortController()
    controller.current = abort
    const queue: number[] = []
    setStates(
      rows.map((_, index) => {
        if (missingByRow[index].length) {
          return {
            status: 'error',
            message: `Missing image: ${missingByRow[index].join(', ')}`,
          }
        }
        queue.push(index)
        return { status: 'waiting' }
      }),
    )
    setOpenRow(null)
    setRunning(true)

    let next = 0
    async function worker() {
      while (next < queue.length && !abort.signal.aborted) {
        const index = queue[next++]
        const row = rows[index]
        updateRow(index, { status: 'checking' })
        try {
          const files = await Promise.all(
            row.labelFiles.map((name) =>
              prepareImage(images.get(name.toLowerCase())!),
            ),
          )
          const result = await verifyLabel(files, row.application, abort.signal)
          updateRow(index, { status: 'done', result })
        } catch (error) {
          if (abort.signal.aborted) {
            updateRow(index, { status: 'waiting' })
            return
          }
          const message =
            error instanceof Error ? error.message : 'The check failed.'
          updateRow(index, { status: 'error', message })
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENT_REQUESTS }, worker))
    setRunning(false)
  }

  async function loadExample() {
    const text = await fetch('/samples/example-batch.csv').then((r) => r.text())
    const parsed = parseBatchCsv(text)
    const names = [...new Set(parsed.rows.flatMap((row) => row.labelFiles))]
    const files = await Promise.all(names.map(fetchSample))
    setImages(new Map(files.map((file) => [file.name.toLowerCase(), file])))
    loadCsv('example-batch.csv', text)
  }

  const counts = FILTERS.map(({ value }) =>
    value === 'all'
      ? states.length
      : states.filter((s) => rowCategory(s) === value).length,
  )

  return (
    <>
      <div className="examples">
        <p>New here? Load a sample spreadsheet and label images:</p>
        <button
          type="button"
          className="usa-button usa-button--outline"
          onClick={loadExample}
          disabled={running}
        >
          Load an example batch
        </button>
      </div>

      <div className="batch-grid">
        <section className="step">
          <h2>
            <span className="step__number" aria-hidden="true">
              1
            </span>
            Prepare a spreadsheet
          </h2>
          <p>
            Put one label application on each row. In the{' '}
            <strong>label_files</strong> column, list the image file names for
            that label, separated by semicolons.
          </p>
          <button
            type="button"
            className="usa-button usa-button--outline"
            onClick={() =>
              downloadFile('label-check-template.csv', templateCsv())
            }
          >
            Download the spreadsheet template
          </button>
        </section>

        <section className="step">
          <h2>
            <span className="step__number" aria-hidden="true">
              2
            </span>
            Add the spreadsheet
          </h2>
          <div className="file-row">
            <label htmlFor={`${id}-csv`} className="usa-button">
              Choose spreadsheet (CSV)
            </label>
            <input
              id={`${id}-csv`}
              className="usa-sr-only"
              type="file"
              accept=".csv,text/csv"
              disabled={running}
              onChange={async (event) => {
                const file = event.target.files?.[0]
                if (file) loadCsv(file.name, await file.text())
                event.target.value = ''
              }}
            />
            {csvName && (
              <span>
                {csvName}: {rows.length}{' '}
                {rows.length === 1 ? 'label' : 'labels'}
              </span>
            )}
          </div>
          {batch && batch.problems.length > 0 && (
            <div className="usa-alert usa-alert--warning usa-alert--slim">
              <div className="usa-alert__body">
                <ul className="usa-alert__text">
                  {batch.problems.slice(0, 10).map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                  {batch.problems.length > 10 && (
                    <li>
                      And {batch.problems.length - 10} more rows with problems.
                    </li>
                  )}
                </ul>
              </div>
            </div>
          )}
        </section>

        <section className="step">
          <h2>
            <span className="step__number" aria-hidden="true">
              3
            </span>
            Add the label images
          </h2>
          <p className="usa-hint">You can select many images at once.</p>
          <div
            className="drop-zone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              addImages(event.dataTransfer.files)
            }}
          >
            <p className="drop-zone__text">Drag label images here, or</p>
            <label
              htmlFor={`${id}-images`}
              className="usa-button usa-button--outline"
            >
              Choose images
            </label>
            <input
              id={`${id}-images`}
              className="usa-sr-only"
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              multiple
              disabled={running}
              onChange={(event) => {
                if (event.target.files) addImages(event.target.files)
                event.target.value = ''
              }}
            />
          </div>
          <p>
            {images.size} {images.size === 1 ? 'image' : 'images'} added.
            {images.size > 0 && !running && (
              <button
                type="button"
                className="usa-button usa-button--unstyled clear-images"
                onClick={() => setImages(new Map())}
              >
                Remove all images
              </button>
            )}
          </p>
          {rows.length > 0 && missingNames.length > 0 && (
            <p className="usa-error-message">
              {missingNames.length} image{' '}
              {missingNames.length === 1 ? 'file is' : 'files are'} named in the
              spreadsheet but not added yet:{' '}
              {missingNames.slice(0, 5).join(', ')}
              {missingNames.length > 5 ? ' and more' : ''}.
            </p>
          )}
        </section>
      </div>

      <div className="actions">
        <button
          type="button"
          className="usa-button usa-button--big"
          onClick={start}
          disabled={running || readyCount === 0}
        >
          {running
            ? 'Checking labels'
            : `Check ${readyCount} ${readyCount === 1 ? 'label' : 'labels'}`}
        </button>
        {running && (
          <button
            type="button"
            className="usa-button usa-button--outline"
            onClick={() => controller.current?.abort()}
          >
            Stop
          </button>
        )}
      </div>

      {states.length > 0 && (
        <section className="step" aria-label="Batch results">
          <h2>Results</h2>
          <progress
            className="batch-progress"
            max={states.length}
            value={finished}
          />
          <p aria-live="polite">
            {finished} of {states.length} checked{running ? '' : '.'}
          </p>

          <div
            className="usa-button-group filter-group"
            role="group"
            aria-label="Show results"
          >
            {FILTERS.map((option, index) => (
              <button
                key={option.value}
                type="button"
                className={`usa-button${filter === option.value ? '' : ' usa-button--outline'}`}
                aria-pressed={filter === option.value}
                onClick={() => setFilter(option.value)}
              >
                {option.label} ({counts[index]})
              </button>
            ))}
          </div>

          <div className="table-scroll">
            <table className="usa-table batch-table">
              <thead>
                <tr>
                  <th scope="col">Label</th>
                  <th scope="col">Brand name</th>
                  <th scope="col">Result</th>
                  <th scope="col">Items to look at</th>
                  <th scope="col">
                    <span className="usa-sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const state = states[index]
                  if (filter !== 'all' && rowCategory(state) !== filter)
                    return null
                  const done = state?.status === 'done' ? state.result : null
                  const issues = done?.fields.filter(
                    (f) => f.status === 'fail' || f.status === 'review',
                  )
                  return (
                    <Fragment key={row.line}>
                      <tr>
                        <td>{row.reference}</td>
                        <td>{row.application.brand_name}</td>
                        <td>
                          {state?.status === 'done' && (
                            <StatusBadge status={state.result.overall} />
                          )}
                          {state?.status === 'checking' && 'Checking'}
                          {state?.status === 'waiting' && 'Waiting'}
                          {state?.status === 'error' && (
                            <span className="row-error">{state.message}</span>
                          )}
                        </td>
                        <td>{issues?.map((f) => f.label).join(', ')}</td>
                        <td>
                          {done && (
                            <button
                              type="button"
                              className="usa-button usa-button--unstyled"
                              aria-expanded={openRow === index}
                              onClick={() =>
                                setOpenRow(openRow === index ? null : index)
                              }
                            >
                              {openRow === index
                                ? 'Hide details'
                                : 'Show details'}
                            </button>
                          )}
                        </td>
                      </tr>
                      {done && openRow === index && (
                        <tr className="batch-table__details">
                          <td colSpan={5}>
                            <Results
                              result={done}
                              files={row.labelFiles.map((name) =>
                                images.get(name.toLowerCase())!,
                              )}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="actions">
            <button
              type="button"
              className="usa-button"
              disabled={finished === 0}
              onClick={() =>
                downloadFile(
                  'label-check-results.csv',
                  resultsCsv(rows, states),
                )
              }
            >
              Download results (CSV)
            </button>
          </div>
        </section>
      )}
    </>
  )
}
