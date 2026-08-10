import { useState } from 'react'
import {useForm} from "react-hook-form"
import { LoginSchema,type loginFormData } from '../../utils/loginScehma'
import { useSelector, useDispatch, } from 'react-redux'
import type { AppDispatch, RootState } from '../../Store/store'
import './loginPage.css'
import {loginUser} from "../../Store/auth/authSlice"
import { useNavigate } from 'react-router-dom'
import { zodResolver } from '@hookform/resolvers/zod'
import {showToastSuccess, showToastError} from "../../toastMessage/toast"
function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)
  const {
    register,
    handleSubmit,
    formState:{isSubmitting,errors},
  } = useForm<loginFormData>({resolver:zodResolver(LoginSchema)});
   const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const {isLoading,error}= useSelector((state:RootState)=>state.authReducer)

  const onSubmit = async(data:loginFormData)=>{
    const { email, password } = data;
    try {
        const res = await dispatch(loginUser({ email, password })).unwrap();
        console.log(res);
        
        showToastSuccess("logged in successfully");
        navigate("/dashboard");
    } catch (err:any) {
        showToastError(err);
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
          <h2>Welcome back</h2>
          <p className="login-subtitle">Sign in to access your agent workspace</p>

          <form className="login-form" onSubmit={handleSubmit(onSubmit)}>
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
                  placeholder="Enter your password"
                  autoComplete="current-password"
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

            <div className="login-row">
              <label className="login-remember">
                <input type="checkbox" name="remember" />
                <span>Remember me</span>
              </label>
              <a href="#" className="login-forgot">
                Forgot password?
              </a>
            </div>

            {error && <p className="login-banner-error">{error}</p>}

            <button type="submit" className="login-submit" disabled={isLoading}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="login-footer">
            Don't have an account? <a href="#">Contact your admin</a>
          </p>
        </div>
      </section>
    </div>
  )
}

export default LoginPage
