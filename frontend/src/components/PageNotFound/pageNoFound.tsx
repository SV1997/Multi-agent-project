import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom'
import './pageNoFound.css'

function PageNotFound() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 404
  const message = isRouteErrorResponse(error)
    ? error.statusText
    : 'The page you are looking for does not exist.'

  return (
    <div className="not-found">
      <p className="not-found-status">{status}</p>
      <h1>Page not found</h1>
      <p className="not-found-message">{message}</p>
      <Link to="/" className="not-found-home">
        Back to home
      </Link>
    </div>
  )
}

export default PageNotFound
