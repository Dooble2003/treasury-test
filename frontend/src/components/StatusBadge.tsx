import type { Overall, Status } from '../api'
import { STATUS_TEXT } from '../status'

function Icon({ status }: { status: Status | Overall }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: '0 0 24 24',
    'aria-hidden': true,
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 3,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
  switch (status) {
    case 'pass':
      return (
        <svg {...common}>
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      )
    case 'review':
      return (
        <svg {...common}>
          <path d="M12 6v8M12 18.5v.5" />
        </svg>
      )
    case 'fail':
    case 'unreadable':
      return (
        <svg {...common}>
          <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <path d="M7 12h10" />
        </svg>
      )
  }
}

export default function StatusBadge({ status }: { status: Status | Overall }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <Icon status={status} />
      {STATUS_TEXT[status]}
    </span>
  )
}
