import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, EMPTY_APPLICATION, verifyLabel } from '../api'
import type { Application, VerifyResponse } from '../api'
import ApplicationForm from '../components/ApplicationForm'
import ImagePicker from '../components/ImagePicker'
import Results from '../components/Results'
import { fetchSample, prepareImage } from '../images'

const OLD_TOM: Application = {
  beverage_type: 'spirits',
  brand_name: 'OLD TOM DISTILLERY',
  class_type: 'Kentucky Straight Bourbon Whiskey',
  alcohol_content: '45% Alc./Vol. (90 Proof)',
  net_contents: '750 mL',
  bottler: 'Old Tom Distillery, Bardstown, KY',
  country_of_origin: '',
}

const EXAMPLES = {
  good: { images: ['bourbon_ok.jpg'], application: OLD_TOM },
  problem: { images: ['bourbon_title_case.jpg'], application: OLD_TOM },
}

type State =
  | { step: 'editing' }
  | { step: 'checking' }
  | { step: 'done'; result: VerifyResponse; files: File[] }
  | { step: 'error'; message: string }

export default function SingleCheck() {
  const [files, setFiles] = useState<File[]>([])
  const [application, setApplication] = useState<Application>(EMPTY_APPLICATION)
  const [state, setState] = useState<State>({ step: 'editing' })
  const [formKey, setFormKey] = useState(0)
  const resultsHeading = useRef<HTMLHeadingElement>(null)
  const imagesHeading = useRef<HTMLHeadingElement>(null)
  const resultsSection = useRef<HTMLElement>(null)
  const errorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (state.step === 'done') {
      // Take the reviewer to the answer. Focus moves too, so keyboard and screen
      // reader users land in the same place.
      resultsHeading.current?.focus({ preventScroll: true })
      resultsSection.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }
    if (state.step === 'error') errorRef.current?.focus()
  }, [state])

  async function check(images: File[], details: Application) {
    if (images.length === 0) {
      setState({
        step: 'error',
        message: 'Add at least one label image first.',
      })
      return
    }
    setState({ step: 'checking' })
    try {
      const prepared = await Promise.all(images.map(prepareImage))
      const result = await verifyLabel(prepared, details)
      setState({ step: 'done', result, files: prepared })
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : 'Something went wrong. Try again.'
      setState({ step: 'error', message })
    }
  }

  async function runExample(name: keyof typeof EXAMPLES) {
    const example = EXAMPLES[name]
    setState({ step: 'checking' })
    try {
      const images = await Promise.all(example.images.map(fetchSample))
      setFiles(images)
      setApplication(example.application)
      await check(images, example.application)
    } catch {
      setState({ step: 'error', message: 'The example could not be loaded.' })
    }
  }

  function startOver() {
    setFiles([])
    setApplication(EMPTY_APPLICATION)
    setState({ step: 'editing' })
    // remount the form so the imported product checkbox resets with it
    setFormKey((key) => key + 1)
    window.scrollTo({ top: 0 })
  }

  // Resubmitted artwork and extra panels belong to the same application, so keep the
  // details and clear only the images.
  function checkAnother() {
    setFiles([])
    setState({ step: 'editing' })
    imagesHeading.current?.focus()
    imagesHeading.current?.scrollIntoView({ block: 'start' })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    check(files, application)
  }

  const checking = state.step === 'checking'
  const hasEntries =
    files.length > 0 ||
    Object.entries(application).some(
      ([key, value]) => key !== 'beverage_type' && value !== '',
    )

  return (
    <>
      <div className="examples">
        <p>New here? See how it works with a sample label:</p>
        <button
          type="button"
          className="usa-button usa-button--outline"
          onClick={() => runExample('good')}
          disabled={checking}
        >
          Example: label that matches
        </button>
        <button
          type="button"
          className="usa-button usa-button--outline"
          onClick={() => runExample('problem')}
          disabled={checking}
        >
          Example: label with a problem
        </button>
      </div>

      <form onSubmit={submit} noValidate>
        <div className="single-grid">
          <section className="step">
            <h2 tabIndex={-1} ref={imagesHeading}>
              <span className="step__number" aria-hidden="true">
                1
              </span>
              Add the label images
            </h2>
            <p className="usa-hint">
              Add the front, back and any other panels of the label.
            </p>
            <ImagePicker files={files} onChange={setFiles} />
            {files.length === 0 && (
              <ul className="image-tips">
                <li>The warning statement is often on the back panel.</li>
                <li>Label artwork from the application reads best.</li>
                <li>JPG, PNG or WEBP, up to six images.</li>
              </ul>
            )}
          </section>

          <section className="step">
            <h2>
              <span className="step__number" aria-hidden="true">
                2
              </span>
              Enter what the application says
            </h2>
            <p className="form-caution">
              Copy these from the application, not from the label. The point is
              to find where the two disagree.
            </p>
            <ApplicationForm
              key={formKey}
              value={application}
              onChange={setApplication}
            />
          </section>
        </div>

        <div className="actions">
          <button
            type="submit"
            className="usa-button usa-button--big"
            disabled={checking}
          >
            {checking ? 'Checking the label' : 'Check label'}
          </button>
          {hasEntries && (
            <button
              type="button"
              className="usa-button usa-button--unstyled"
              onClick={startOver}
            >
              Clear the form
            </button>
          )}
        </div>
      </form>

      <div aria-live="polite">
        {checking && (
          <p className="checking">
            <span className="spinner" aria-hidden="true" /> Checking the label.
            This usually takes a few seconds.
          </p>
        )}
      </div>

      {state.step === 'error' && (
        <div
          className="usa-alert usa-alert--error usa-alert--slim"
          role="alert"
          tabIndex={-1}
          ref={errorRef}
        >
          <div className="usa-alert__body">
            <p className="usa-alert__text">{state.message}</p>
          </div>
        </div>
      )}

      {state.step === 'done' && (
        <section className="step" aria-label="Results" ref={resultsSection}>
          <Results
            result={state.result}
            files={state.files}
            headingRef={resultsHeading}
          />
          <div className="actions actions--static">
            <button
              type="button"
              className="usa-button usa-button--big"
              onClick={checkAnother}
            >
              Check another label with these details
            </button>
            <button
              type="button"
              className="usa-button usa-button--outline"
              onClick={startOver}
            >
              Start a new label
            </button>
          </div>
        </section>
      )}
    </>
  )
}
