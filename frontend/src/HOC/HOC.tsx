import { Navigate } from "react-router-dom"
import type { ComponentType } from "react"
import { showToastError } from "../toastMessage/toast"
import { jwtDecode } from "jwt-decode"
export const ProtectedRoute = (allowedRoles: string[])=><P extends object>(Component: ComponentType<P>) => (props: P) => {
    const token = localStorage.getItem("accessToken")
    if(!token) return <Navigate to="/login"replace/>
    const user = jwtDecode<{ role: string }>(token)
    const role=user.role
    if(!allowedRoles.includes(role) && allowedRoles.length>0){
        showToastError("you cannot access page registered for admin")
        return <Navigate to="/dashboard" replace />
    }

    return <Component {...props} />

}

export const PublicRoute = <P extends object>(Component: ComponentType<P>) => (props: P) => {
    const token = localStorage.getItem('accessToken')
    if(token) return <Navigate to="/dashboard" replace />
    return <Component {...props} />
}

