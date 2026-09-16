import { useEffect, useState, type CSSProperties, type Ref } from 'react'
import type {
  FieldResult,
  Overall,
  Status,
  VerifyResponse,
  WarningDetail,
} from '../api'
import ImageViewer from './ImageViewer'
import StatusBadge from './StatusBadge'

const SUMMARY: Record<Overall, { title: string; alert: string }> = {
  pass: { title: 'All checks passed', alert: 'success' },
  review: { title: 'Some items need review', alert: 'warning' },
  fail: { title: 'Problems found', alert: 'error' },
  unreadable: { title: 'The label could not be read', alert: 'info' },
}

const ANSWER: Record<Status, string> = {
  pass: 'Yes',
  review: 'Not sure',
  fail: 'No',
  not_checked: 'Not checked',
}

interface Props {
  result: VerifyResponse
  files: File[]
  headingRef?: Ref<HTMLHeadingElement>
  printable?: boolean
}

export default function Results({
  result,
  files,
  headingRef,
  printable,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [opened, setOpened] = useState<string[]>([])
  const [printRequest, setPrintRequest] = useState(0)

  // Collapsed items are not in the page, so a print stylesheet cannot bring them back.
  // Open everything, let React commit it, then print.
  useEffect(() => {
    if (printRequest) window.print()
  }, [printRequest])
  const boxes =
    result.fields.find((field) => field.key === selected)?.boxes ?? []
  const summary = SUMMARY[result.overall]
  const seconds = (result.elapsed_ms / 1000).toFixed(1)
  const needsAttention = result.fields.filter(
    (field) => field.status === 'fail' || field.status === 'review',
  ).length

  // Items that passed collapse to one line so the ones needing a decision are the
  // page, not a scroll away.
  const expanded = (field: FieldResult) =>
    showAll ||
    opened.includes(field.key) ||
    field.status === 'fail' ||
    field.status === 'review'

  return (
    <div className="results">
      <p className="results__print-header">
        Label Check: {files.map((file) => file.name).join(', ')}
      </p>
      <div className={`usa-alert usa-alert--${summary.alert}`}>
        <div className="usa-alert__body">
          <h2 className="usa-alert__heading" tabIndex={-1} ref={headingRef}>
            {summary.title}
          </h2>
          <p className="usa-alert__text">
            {result.message} Checked in {seconds} seconds.
          </p>
          {needsAttention > 0 && (
            <p className="results__attention">
              {needsAttention} of {result.fields.length} items need your
              attention. They are open below.
            </p>
          )}
          <div className="results__actions">
            {result.fields.length > 0 && (
              <button
                type="button"
                className="usa-button usa-button--unstyled results__toggle"
                onClick={() => setShowAll(!showAll)}
              >
                {showAll
                  ? 'Collapse the items that matched'
                  : `Show details for all ${result.fields.length} items`}
              </button>
            )}
            {printable && (
              <button
                type="button"
                className="usa-button usa-button--unstyled results__toggle"
                onClick={() => {
                  setShowAll(true)
                  setPrintRequest((count) => count + 1)
                }}
              >
                Print these results
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="results__layout">
        {result.fields.length > 0 && (
          <ol className="checklist">
            {result.fields.map((field, index) => {
              const open = expanded(field)
              return (
                <li
                  key={field.key}
                  style={{ '--row': index } as CSSProperties}
                  className={[
                    'checklist__item',
                    `checklist__item--${field.status}`,
                    selected === field.key ? 'is-selected' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  <div className="checklist__head">
                    <h3>{field.label}</h3>
                    <div className="checklist__head-right">
                      <StatusBadge status={field.status} />
                      {field.status !== 'fail' && field.status !== 'review' && (
                        <button
                          type="button"
                          className="usa-button usa-button--unstyled checklist__toggle"
                          aria-expanded={open}
                          onClick={() =>
                            setOpened(
                              open
                                ? opened.filter((key) => key !== field.key)
                                : [...opened, field.key],
                            )
                          }
                        >
                          {open ? 'Hide' : 'Details'}
                        </button>
                      )}
                    </div>
                  </div>
                  {open && (
                    <>
                      <dl className="checklist__values">
                        {field.expected &&
                          field.key !== 'government_warning' && (
                            <>
                              <dt>Application says</dt>
                              <dd>{field.expected}</dd>
                            </>
                          )}
                        {field.found && field.key !== 'government_warning' && (
                          <>
                            <dt>Label says</dt>
                            <dd>{field.found}</dd>
                          </>
                        )}
                      </dl>
                      {field.note && (
                        <p className="checklist__note">{field.note}</p>
                      )}
                      {field.key === 'government_warning' && result.warning && (
                        <WarningDetails detail={result.warning} />
                      )}
                    </>
                  )}
                  {open && field.boxes.length > 0 && (
                    <button
                      type="button"
                      className="usa-button usa-button--unstyled"
                      aria-pressed={selected === field.key}
                      onClick={() =>
                        setSelected(selected === field.key ? null : field.key)
                      }
                    >
                      {selected === field.key
                        ? 'Hide on image'
                        : 'Show on image'}
                    </button>
                  )}
                </li>
              )
            })}
          </ol>
        )}
        <div className="results__image">
          <ImageViewer files={files} images={result.images} boxes={boxes} />
        </div>
      </div>
    </div>
  )
}

function WarningDetails({ detail }: { detail: WarningDetail }) {
  const hasDifferences = detail.diff.some((part) => part.kind !== 'same')
  const checks: [string, Status][] = [
    ['"GOVERNMENT WARNING" is in capital letters', detail.heading_caps],
    ['"GOVERNMENT WARNING" is in bold', detail.heading_bold],
    ['Wording matches the required statement', detail.wording],
  ]

  return (
    <div className="warning-detail">
      <ul className="warning-detail__checks">
        {checks.map(([text, status]) => (
          <li key={text}>
            <span className={`answer answer--${status}`}>{ANSWER[status]}</span>
            {text}
          </li>
        ))}
      </ul>

      {detail.heading_crop && (
        <figure className="warning-detail__crop">
          <img
            src={detail.heading_crop}
            alt="Close-up of the warning heading as printed"
          />
          <figcaption>Warning heading as printed on the label</figcaption>
        </figure>
      )}

      {hasDifferences && (
        <>
          <h4>Differences from the required wording</h4>
          <p className="diff">
            {detail.diff.map((part, index) => (
              <DiffText
                key={index}
                kind={part.kind}
                expected={part.expected}
                found={part.found}
              />
            ))}
          </p>
          <p className="usa-hint">
            Crossed-out words are required. Highlighted words are what the label
            says instead.
          </p>
        </>
      )}
    </div>
  )
}

function DiffText({ kind, expected, found }: WarningDetail['diff'][number]) {
  if (kind === 'same') return <>{expected} </>
  return (
    <>
      {expected && (
        <del>
          <span className="usa-sr-only">required: </span>
          {expected}
        </del>
      )}{' '}
      {found && (
        <ins>
          <span className="usa-sr-only">label says: </span>
          {found}
        </ins>
      )}{' '}
    </>
  )
}
