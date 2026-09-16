import { useEffect, useId, useMemo, useState } from 'react'
import { ACCEPTED_TYPES } from '../images'

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  maxFiles?: number
}

export default function ImagePicker({ files, onChange, maxFiles = 6 }: Props) {
  const inputId = useId()
  const [dragging, setDragging] = useState(false)
  const [message, setMessage] = useState('')

  const previews = useMemo(
    () => files.map((file) => URL.createObjectURL(file)),
    [files],
  )
  useEffect(
    () => () => previews.forEach((url) => URL.revokeObjectURL(url)),
    [previews],
  )

  function add(list: FileList | null) {
    if (!list) return
    const incoming = Array.from(list)
    const images = incoming.filter(
      (file) => ACCEPTED_TYPES.includes(file.type) || file.type === '',
    )
    const skipped = incoming.length - images.length
    const next = [...files, ...images].slice(0, maxFiles)
    const notes = []
    if (skipped)
      notes.push(`${skipped} file(s) skipped: use JPG, PNG or WEBP images.`)
    if (files.length + images.length > maxFiles)
      notes.push(`Only ${maxFiles} images can be added for one label.`)
    setMessage(notes.join(' '))
    onChange(next)
  }

  return (
    <div>
      <div
        className={`drop-zone${dragging ? ' drop-zone--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          add(event.dataTransfer.files)
        }}
      >
        <p className="drop-zone__text">Drag label images here, or</p>
        <label htmlFor={inputId} className="usa-button usa-button--outline">
          Choose images
        </label>
        <input
          id={inputId}
          className="usa-sr-only"
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          multiple
          onChange={(event) => {
            add(event.target.files)
            event.target.value = ''
          }}
        />
      </div>
      {message && (
        <p className="usa-error-message" role="alert">
          {message}
        </p>
      )}
      {files.length > 0 && (
        <ul className="thumbnails" aria-label="Added images">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="thumbnail">
              <img src={previews[index]} alt="" />
              <span className="thumbnail__name">{file.name}</span>
              <button
                type="button"
                className="usa-button usa-button--unstyled"
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                Remove<span className="usa-sr-only"> {file.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
