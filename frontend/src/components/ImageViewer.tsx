import { useEffect, useMemo, useState } from 'react'
import type { Box, ImageInfo } from '../api'

interface Props {
  files: File[]
  images: ImageInfo[]
  boxes: Box[]
}

export default function ImageViewer({ files, images, boxes }: Props) {
  // A newly selected field jumps to the image it was found on; picking a tab afterwards
  // overrides that until the selection changes again.
  const [picked, setPicked] = useState({ index: 0, boxes })
  const active =
    picked.boxes === boxes || boxes.length === 0 ? picked.index : boxes[0].image
  const setActive = (index: number) => setPicked({ index, boxes })

  const urls = useMemo(
    () => files.map((file) => URL.createObjectURL(file)),
    [files],
  )
  useEffect(() => () => urls.forEach((url) => URL.revokeObjectURL(url)), [urls])

  const info = images[active]
  const shown = boxes.filter((box) => box.image === active)

  return (
    <div className="image-viewer">
      {files.length > 1 && (
        <div
          className="image-viewer__tabs"
          role="group"
          aria-label="Label images"
        >
          {files.map((file, index) => (
            <button
              key={`${file.name}-${index}`}
              type="button"
              className={`usa-button${index === active ? '' : ' usa-button--outline'}`}
              aria-pressed={index === active}
              onClick={() => setActive(index)}
            >
              Image {index + 1}
            </button>
          ))}
        </div>
      )}
      <div className="image-viewer__frame">
        <img
          src={urls[active]}
          alt={`Label image ${active + 1}: ${files[active]?.name}`}
        />
        {info && (
          <svg
            viewBox={`0 0 ${info.width} ${info.height}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {shown.map((box, index) => (
              <polygon
                key={index}
                className="image-viewer__highlight"
                points={box.points.map((point) => point.join(',')).join(' ')}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
        )}
      </div>
      {info?.notes.length ? (
        <ul className="image-viewer__notes">
          {info.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
