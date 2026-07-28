import { Navigate } from "react-router-dom"
import type { ComponentType } from "react"

export const ProtectedRoute = <P extends object>(Component: ComponentType<P>) => (props: P) => {
    const token = localStorage.getItem("accessToken")
    if(!token) return <Navigate to="/login"replace/>
    return <Component {...props} />
}

export const PublicRoute = <P extends object>(Component: ComponentType<P>) => (props: P) => {
    const token = localStorage.getItem('accessToken')
    if(token) return <Navigate to="/dashboard" replace />
    return <Component {...props} />
}