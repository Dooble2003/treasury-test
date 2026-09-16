// The server shrinks anything larger than this anyway, so sending more only slows uploads.
const MAX_EDGE = 3200
const MAX_UNTOUCHED_BYTES = 3 * 1024 * 1024

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export async function prepareImage(file: File): Promise<File> {
  if (file.size <= MAX_UNTOUCHED_BYTES) return file

  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    // Let the server report formats the browser can't decode.
    return file
  }

  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.92),
  )
  if (!blob) return file
  const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
  return new File([blob], name, { type: 'image/jpeg' })
}

export async function fetchSample(name: string): Promise<File> {
  const response = await fetch(`/samples/${name}`)
  if (!response.ok) throw new Error(`Sample ${name} is missing`)
  const blob = await response.blob()
  return new File([blob], name, { type: blob.type })
}
