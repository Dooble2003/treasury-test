export type Status = 'pass' | 'review' | 'fail' | 'not_checked'
export type Overall = 'pass' | 'review' | 'fail' | 'unreadable'
export type BeverageType = 'spirits' | 'wine' | 'beer'

export interface Application {
  beverage_type: BeverageType
  brand_name: string
  class_type: string
  alcohol_content: string
  net_contents: string
  bottler: string
  country_of_origin: string
}

export interface Box {
  image: number
  points: number[][]
}

export interface FieldResult {
  key: string
  label: string
  status: Status
  expected: string
  found: string
  note: string
  boxes: Box[]
}

export interface DiffPart {
  kind: 'same' | 'missing' | 'extra' | 'changed'
  expected: string
  found: string
}

export interface WarningDetail {
  heading_caps: Status
  heading_bold: Status
  wording: Status
  diff: DiffPart[]
  heading_crop: string
}

export interface ImageInfo {
  index: number
  width: number
  height: number
  notes: string[]
}

export interface VerifyResponse {
  overall: Overall
  message: string
  fields: FieldResult[]
  warning: WarningDetail | null
  images: ImageInfo[]
  elapsed_ms: number
}

export const EMPTY_APPLICATION: Application = {
  beverage_type: 'spirits',
  brand_name: '',
  class_type: '',
  alcohol_content: '',
  net_contents: '',
  bottler: '',
  country_of_origin: '',
}

export class ApiError extends Error {}

const MAX_BUSY_RETRIES = 6
// A request can wait up to 30 seconds for its turn on the server and then take a few
// seconds to read. Past this, something is wrong and the reviewer should hear about it
// rather than watch the spinner.
const REQUEST_TIMEOUT_MS = 60_000

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

export async function verifyLabel(
  images: File[],
  application: Application,
  signal?: AbortSignal,
): Promise<VerifyResponse> {
  const body = new FormData()
  images.forEach((image) => body.append('images', image))
  body.append('application', JSON.stringify(application))

  for (let attempt = 0; ; attempt++) {
    let response: Response
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    try {
      response = await fetch('/api/verify', {
        method: 'POST',
        body,
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      })
    } catch (error) {
      if (signal?.aborted) throw error
      if (timeout.aborted) {
        throw new ApiError(
          'The checker did not answer in time. Try again, or check this label on its own.',
        )
      }
      throw new ApiError(
        'Could not reach the checker. Check your connection and try again.',
      )
    }

    // During a large batch the server may be busy; wait and retry quietly.
    if (response.status === 503 && attempt < MAX_BUSY_RETRIES) {
      const seconds = Number(response.headers.get('Retry-After')) || 3
      await wait(seconds * 1000, signal)
      continue
    }
    if (!response.ok) {
      const detail = await response
        .json()
        .then((data) => data?.detail)
        .catch(() => null)
      throw new ApiError(
        typeof detail === 'string'
          ? detail
          : 'Something went wrong while checking this label. Try again.',
      )
    }
    return response.json()
  }
}
