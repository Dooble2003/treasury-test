import type { Overall, Status } from './api'

export const STATUS_TEXT: Record<Status | Overall, string> = {
  pass: 'Matches',
  review: 'Needs review',
  fail: 'Does not match',
  not_checked: 'Not checked',
  unreadable: 'Could not read',
}
