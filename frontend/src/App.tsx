import { useEffect, useState } from 'react'
import BatchCheck from './pages/BatchCheck'
import SingleCheck from './pages/SingleCheck'

type Mode = 'single' | 'batch'

const MODES: { value: Mode; label: string }[] = [
  { value: 'single', label: 'One label' },
  { value: 'batch', label: 'Many labels' },
]

function App() {
  const [mode, setMode] = useState<Mode>(() =>
    window.location.hash === '#batch' ? 'batch' : 'single',
  )

  useEffect(() => {
    const url = mode === 'batch' ? '#batch' : window.location.pathname
    window.history.replaceState(null, '', url)
  }, [mode])

  return (
    <>
      <a className="usa-skipnav" href="#main">
        Skip to main content
      </a>
      <div className="prototype-banner">
        Prototype for evaluation only. This is not an official government
        system.
      </div>
      <header className="app-header">
        <div className="app-container app-header__inner">
          <div>
            <h1>Label Check</h1>
            <p>Compare an alcohol label with what the application says.</p>
          </div>
          <div
            className="mode-switch"
            role="group"
            aria-label="What do you want to check?"
          >
            {MODES.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`mode-switch__button${mode === option.value ? ' is-active' : ''}`}
                aria-pressed={mode === option.value}
                onClick={() => setMode(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main id="main" className="app-container">
        {/* Both stay mounted so a running batch keeps going while the other tab is open. */}
        <div hidden={mode !== 'single'}>
          <SingleCheck />
        </div>
        <div hidden={mode !== 'batch'}>
          <BatchCheck />
        </div>
      </main>
    </>
  )
}

export default App
