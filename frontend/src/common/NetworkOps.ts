import axios from 'axios'
import config from './config'

const API_TIMEOUT = 18000;

const authRoutes = [
    config.ingestion.INGESTION,
    config.query.QUERY,
    config.query.QUERY_RESUME,
    config.query.QUERY_STREAM,
    config.query.QUERY_STREAM_RESUME,
    config.query.QUERY_RESOLVE_REVIEW,
    config.query.QUERY_FLAG,
    config.session.SESSION,
]

let isRefreshing = false;
let failedQueue: Array<{resolve: Function, reject: Function}>=[]

const processQueue = (error:any, token:string|null=null)=>{
failedQueue.forEach(({resolve,reject})=>{
    if(error) reject(error)
    else resolve(token)
})
failedQueue=[]
}

const baseUrl = import.meta.env.VITE_BASE_URL;
const api = axios.create({ baseURL: baseUrl })

if (import.meta.hot) {
    import.meta.hot.dispose(() => {
        api.interceptors.request.clear?.()
        api.interceptors.response.clear?.()
    })
}

api.interceptors.request.use(
    (requestConfig) => {
        const accessToken = localStorage.getItem("accessToken");
        try {
            const requestUrl = requestConfig.url?.split("?")[0] || ""
            const isTokenRequired = authRoutes.some((route) => requestUrl === route || requestUrl.startsWith(`${route}/`))
            requestConfig.timeout = API_TIMEOUT
            if (isTokenRequired && accessToken) {
                requestConfig.headers.Authorization = `Bearer ${accessToken}`
            }
        } catch (error) {
            throw new Error("Error in request interceptor" + error)
        }
        return requestConfig
    }
)

api.interceptors.response.use(
    (response) => {        
        try {
            if (config.SUCCESS_CODE.includes(response.status)) {
                return response.data
            } else {
                console.error("Unexpected response status:", response);
                return Promise.reject(new Error("Unexpected response status"));
            }
        } catch (error) {
            console.log(error);
            throw new Error("Error in response interceptor" + error)
        }
    },
    async(error) => {
        const req = error.config;

        if (error.response) {
            if(error.response?.status!==401){
                return Promise.reject(error.response.data)
            }
            console.log(error.response.status, req.url);
            if(req.url.includes('/auth/refresh')){
            localStorage.clear();
            window.location.href="/login";
            return Promise.reject(error)
        }

        if(isRefreshing){
            return new Promise((resolve, reject)=>{
                failedQueue.push({resolve,reject})
            }).then(token=>{
                req.headers["Authorization"] = `Bearer ${token}`
                return api(req)
            }
            )
        }
        isRefreshing = true
        try {
            const response:any = await api.post("/auth/refresh",{},{
                withCredentials:true
            })
            console.log(response);
            
            const newToken = response.accessToken
            localStorage.setItem('accessToken', newToken)
            processQueue(null, newToken)
            req.headers["Authorization"] = `Bearer ${newToken}`
            return api(req)
        } catch (error) {
            processQueue(error, null)
            console.log(error);
            
            localStorage.clear()
            window.location.href = "/login"
            return Promise.reject(error)
        }finally {
    isRefreshing = false
}
            
        } else if (error.request) {
            console.error("Request error:", error.request);
            return Promise.reject(new Error("No response received from server"));
        } else {
            console.error("Error in request setup:", error.message);
            return Promise.reject(new Error(error.message));
        }
    }
)

export const fetchRequestGet = async (url: string) => {
    try {
        const response = await api.get(baseUrl + url, {
            headers: { "Content-Type": "application/json" },
            withCredentials: true
        })
        return response
    } catch (error) {
        console.error("error in GET request:", error)
        return Promise.reject(error)
    }
}

export const fetchRequestPost = async (url: string, body = {}) => {
    try {
        const response = await api.post(baseUrl + url, body, {
            headers: { "Content-Type": "application/json" },
            withCredentials: true
        })
        return response
    } catch (error) {
        console.error("error in POST request:", error)
        return Promise.reject(error)
    }
}

export const fetchRequestPostFormData = async (url: string, formData: FormData) => {
    try {
        // no explicit Content-Type — axios/browser sets the multipart boundary automatically
        const response = await api.post(baseUrl + url, formData, {
            withCredentials: true
        })
        return response
    } catch (error) {
        console.error("error in POST (form-data) request:", error)
        return Promise.reject(error)
    }
}

export const fetchRequestPut = async (url: string, body = {}) => {
    try {
        const response = await api.put(baseUrl + url, body, {
            headers: { "Content-Type": "application/json" },
            withCredentials: true
        })
        return response
    } catch (error) {
        console.error("error in PUT request:", error)
        return Promise.reject(error)
    }
}

export const fetchRequesDelete = async (url: string, payload = {}) => {
    try {
        const response = await api.delete(baseUrl + url, { data: payload })
        return response
    } catch (error) {
        console.error("Error in DELETE request:", error);
        return Promise.reject(error);
    }
};