import './customErorPage.css'

interface CustomErrorPageProps {
  componentName: string
  error?: unknown
  resetErrorBoundary?: (...args: unknown[]) => void
}

function getErrorMessage(error: unknown): string | undefined {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return undefined
}

function CustomErrorPage({ componentName, error, resetErrorBoundary }: CustomErrorPageProps) {
  const message = getErrorMessage(error)

  return (
    <div className="custom-error">
      <p className="custom-error-status">Something went wrong</p>
      <h1>Error in {componentName}</h1>
      {message && <p className="custom-error-message">{message}</p>}
      {resetErrorBoundary && (
        <button
          type="button"
          className="custom-error-retry"
          onClick={() => resetErrorBoundary()}
        >
          Try again
        </button>
      )}
    </div>
  )
}

export default CustomErrorPage
