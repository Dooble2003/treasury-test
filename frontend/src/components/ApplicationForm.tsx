import { useId, useState } from 'react'
import type { Application, BeverageType } from '../api'

interface Props {
  value: Application
  onChange: (value: Application) => void
}

type TextField = Exclude<keyof Application, 'beverage_type'>

const TEXT_FIELDS: {
  key: TextField
  label: string
  hint: string
  wide?: true
}[] = [
  {
    key: 'brand_name',
    label: 'Brand name',
    hint: 'Example: OLD TOM DISTILLERY',
  },
  {
    key: 'class_type',
    label: 'Class or type',
    hint: 'Example: Kentucky Straight Bourbon Whiskey',
  },
  {
    key: 'alcohol_content',
    label: 'Alcohol content',
    hint: 'Example: 45% Alc./Vol. Leave blank if the application does not state it.',
  },
  { key: 'net_contents', label: 'Net contents', hint: 'Example: 750 mL' },
  {
    key: 'bottler',
    label: 'Bottler or producer name and address',
    hint: 'Example: Old Tom Distillery, Bardstown, KY',
    wide: true,
  },
]

export default function ApplicationForm({ value, onChange }: Props) {
  const id = useId()
  const [imported, setImported] = useState(Boolean(value.country_of_origin))
  const showCountry = imported || Boolean(value.country_of_origin)

  function set<K extends keyof Application>(
    key: K,
    fieldValue: Application[K],
  ) {
    onChange({ ...value, [key]: fieldValue })
  }

  return (
    <div className="application-form">
      <div className="field field--wide">
        <label className="usa-label" htmlFor={`${id}-type`}>
          Type of product
        </label>
        <select
          className="usa-select"
          id={`${id}-type`}
          value={value.beverage_type}
          onChange={(event) =>
            set('beverage_type', event.target.value as BeverageType)
          }
        >
          <option value="spirits">Distilled spirits</option>
          <option value="wine">Wine</option>
          <option value="beer">Beer or malt beverage</option>
        </select>
      </div>

      {TEXT_FIELDS.map((field) => (
        <div
          key={field.key}
          className={`field${field.wide ? ' field--wide' : ''}`}
        >
          <label className="usa-label" htmlFor={`${id}-${field.key}`}>
            {field.label}
          </label>
          <span className="usa-hint" id={`${id}-${field.key}-hint`}>
            {field.hint}
          </span>
          <input
            className="usa-input"
            id={`${id}-${field.key}`}
            aria-describedby={`${id}-${field.key}-hint`}
            value={value[field.key]}
            onChange={(event) => set(field.key, event.target.value)}
            autoComplete="off"
          />
        </div>
      ))}

      <div className="usa-checkbox imported-checkbox field--wide">
        <input
          className="usa-checkbox__input"
          id={`${id}-imported`}
          type="checkbox"
          checked={showCountry}
          onChange={(event) => {
            setImported(event.target.checked)
            if (!event.target.checked) set('country_of_origin', '')
          }}
        />
        <label className="usa-checkbox__label" htmlFor={`${id}-imported`}>
          This is an imported product
        </label>
      </div>
      {showCountry && (
        <div className="field field--wide">
          <label className="usa-label" htmlFor={`${id}-country`}>
            Country of origin
          </label>
          <input
            className="usa-input"
            id={`${id}-country`}
            value={value.country_of_origin}
            onChange={(event) => set('country_of_origin', event.target.value)}
            autoComplete="off"
          />
        </div>
      )}
    </div>
  )
}
