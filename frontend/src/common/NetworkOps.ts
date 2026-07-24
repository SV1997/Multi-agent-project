import axios from 'axios'
import config from './config'

const API_TIMEOUT = 18000;

const authRoutes = [
    config.ingestion.INGESTION,
    config.query.QUERY,
    config.query.QUERY_RESUME,
    config.query.QUERY_STREAM,
    config.query.QUERY_STREAM_RESUME,
    config.query.QUERY_FLAG,
]

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
            const isTokenRequired = authRoutes.includes(requestConfig.url?.split("?")[0] || "")
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
            throw new Error("Error in response interceptor" + error)
        }
    },
    (error) => {
        if (error.response) {
            return Promise.reject(error.response.data)
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