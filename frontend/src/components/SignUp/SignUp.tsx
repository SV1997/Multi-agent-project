import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { SignUpSchema, type signUpFormData } from '../../utils/signUpSchema'
import { useSelector, useDispatch } from 'react-redux'
import type { AppDispatch, RootState } from '../../Store/store'
import '../Login/loginPage.css'
import { registerUser } from '../../Store/auth/authSlice'
import { Link, useNavigate } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import { showToastSuccess, showToastError } from '../../toastMessage/toast'

function SignUp() {
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { isSubmitting, errors },
  } = useForm<signUpFormData>({ resolver: zodResolver(SignUpSchema) })
  const dispatch = useDispatch<AppDispatch>()
  const navigate = useNavigate()
  const { isLoading, error } = useSelector((state: RootState) => state.authReducer)

  const onSubmit = async (data: signUpFormData) => {
    const { name, email, password } = data
    try {
      const res = await dispatch(registerUser({ name, email, password })).unwrap()
      console.log(res)

      showToastSuccess('Account created successfully')
      navigate('/login')
    } catch (err: any) {
      showToastError(err)
    }
  }

  return (
    <div className="login-page">
      <section className="login-brand">
        <div className="login-orbit" aria-hidden="true">
          <div className="login-orbit-ring login-orbit-ring--outer">
            <span className="login-node" />
            <span className="login-node" />
            <span className="login-node" />
          </div>
          <div className="login-orbit-ring login-orbit-ring--inner">
            <span className="login-node" />
            <span className="login-node" />
          </div>
          <div className="login-orbit-core">RAG</div>
        </div>

        <div className="login-brand-content">
          <div className="login-logo">
            <span className="login-logo-mark">⟡</span>
            <span className="login-logo-text">Orchestra</span>
          </div>
          <h1>Multi-agent RAG, orchestrated.</h1>
          <p>
            Route every query through specialized retrieval agents, coordinated
            by a central orchestrator, for grounded answers you can trust.
          </p>

          <ul className="login-feature-list">
            <li>
              <span className="login-feature-dot" />
              Agent-to-agent task orchestration
            </li>
            <li>
              <span className="login-feature-dot" />
              Retrieval-augmented reasoning pipelines
            </li>
            <li>
              <span className="login-feature-dot" />
              Human-in-the-loop review &amp; feedback
            </li>
          </ul>
        </div>
      </section>

      <section className="login-form-panel">
        <div className="login-card">
          <div className="login-card-logo">
            <span className="login-logo-mark">⟡</span>
            <span className="login-logo-text">Orchestra</span>
          </div>
          <h2>Create your account</h2>
          <p className="login-subtitle">Set up access to your agent workspace</p>

          <form className="login-form" onSubmit={handleSubmit(onSubmit)}>
            <label className="login-field">
              <span className="login-label">Name</span>
              <input
                type="text"
                placeholder="Jane Doe"
                autoComplete="name"
                {...register('name')}
              />
              {errors.name && (
                <span className="login-error">{errors.name.message}</span>
              )}
            </label>

            <label className="login-field">
              <span className="login-label">Email</span>
              <input
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                {...register('email')}
              />
              {errors.email && (
                <span className="login-error">{errors.email.message}</span>
              )}
            </label>

            <label className="login-field">
              <span className="login-label">Password</span>
              <div className="login-password-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Create a password"
                  autoComplete="new-password"
                  {...register('password')}
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              {errors.password && (
                <span className="login-error">{errors.password.message}</span>
              )}
            </label>

            <label className="login-field">
              <span className="login-label">Confirm password</span>
              <div className="login-password-wrap">
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  placeholder="Re-enter your password"
                  autoComplete="new-password"
                  {...register('confirmPassword')}
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowConfirmPassword((prev) => !prev)}
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              {errors.confirmPassword && (
                <span className="login-error">{errors.confirmPassword.message}</span>
              )}
            </label>

            {error && <p className="login-banner-error">{error}</p>}

            <button type="submit" className="login-submit" disabled={isLoading}>
              {isSubmitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="login-footer">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </section>
    </div>
  )
}

export default SignUp
