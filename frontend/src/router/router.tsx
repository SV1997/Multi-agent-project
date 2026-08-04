import { createBrowserRouter } from "react-router-dom";
import { lazy, Suspense } from "react";
import { Outlet } from "react-router-dom";
import { ErrorBoundary } from "react-error-boundary";
import Loader from "../components/Loader/loader";
import PageNotFound from "../components/PageNotFound/pageNoFound";
import CustomErrorPage from "../components/CustomErorPage/customErorPage";
import { ProtectedRoute, PublicRoute } from "../HOC/HOC";
const LoginPage = PublicRoute(lazy(() => (import("../components/Login/loginPage"))));
const SignUpPage = PublicRoute(lazy(() => import("../components/SignUp/SignUp")));
const DashboardPage = ProtectedRoute([])(lazy(()=>import("../components/Dashboard/Dashboard")))
const ProtectedDashboardPage = DashboardPage
const AdminReview =  ProtectedRoute(["admin"])(lazy(()=>import("../components/AdminReview/AdminReview")))
const Ingestion =  ProtectedRoute(["admin"])(lazy(()=>import("../components/Ingestion/Ingestion")))
export const router = createBrowserRouter([
    {
        path: "/",
        element: <Outlet />,
        errorElement: <PageNotFound />,
        children: [{
            index:true,
            element:<Suspense fallback={<Loader />}></Suspense>
        },
            {
                path: "login",
                element: (
                    <ErrorBoundary
                        fallbackRender={(props) => (
                            <CustomErrorPage {...props} componentName="LoginPage" />
                        )}
                    >
                        <Suspense fallback={<Loader />}>
                            <LoginPage />
                        </Suspense>
                    </ErrorBoundary>
                ),
            },
            {
                path: "signup",
                element: (
                    <ErrorBoundary
                        fallbackRender={(props) => (
                            <CustomErrorPage {...props} componentName="SignUp" />
                        )}
                    >
                        <Suspense fallback={<Loader />}>
                            <SignUpPage />
                        </Suspense>
                    </ErrorBoundary>
                ),
            },
            {
                path: "dashboard/:sessionId?",
                element:(
                    <ErrorBoundary fallbackRender={(props)=>(
                        <CustomErrorPage {...props} componentName="Dashboard"/>
                    )

                    }>
                        <Suspense fallback={<Loader/>}>
                        <ProtectedDashboardPage/>
                        </Suspense>
                    </ErrorBoundary>
                )
            },
            {
                path:"adminReview",
                element:(
                    <ErrorBoundary fallbackRender={(props)=>
                        <CustomErrorPage {...props} componentName="admin review"/>
                    }>
                        <Suspense fallback={<Loader></Loader>}>
                        <AdminReview/>
                        </Suspense>

                    </ErrorBoundary>
                )
            },
            {
                path:"ingestion",
                element:(
                    <ErrorBoundary fallbackRender={(props)=>
                        <CustomErrorPage {...props} componentName="ingestion"/>
                    }>
                        <Suspense fallback={<Loader></Loader>}>
                        <Ingestion/>
                        </Suspense>

                    </ErrorBoundary>
                )
            }
        ],
    },
]);