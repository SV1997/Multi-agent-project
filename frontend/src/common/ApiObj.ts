const ApiObj = {
    baseUrl: import.meta.env.VITE_BASE_URL,
    auth:{
        LOGIN: '/auth/login',
        REGISTER: '/auth/register',
        REFRESH: '/auth/refresh',
        LOGOUT: '/auth/logout',
    },
    query:{
        QUERY: '/query',
        QUERY_RESUME: '/query/resume',
        QUERY_STREAM: '/query/stream',
        QUERY_STREAM_RESUME: '/query/stream/resume',
        QUERY_RESOLVE_REVIEW: '/query/resolve-review',
        QUERY_FLAG: '/query/flag',
        QUERY_PENDING_REVIEWS: '/query/pending-reviews',
        QUERY_NOTIFICATIONS: (thread_id: string) => `/query/notifications/${thread_id}`,
        QUERY_MY_PENDING_REVIEWS: '/query/my-pending-reviews',
    },
    evaluate:{
        EVALUATE: (threadId: string) => `/evaluate/${threadId}`,
    },
    session:{
        SESSION_CREATE: '/session/create',
        SESSION_LIST: '/session/list',
        SESSION_MESSAGES: (id: string) => `/session/${id}/messages`,
    },
    ingestion:{
        INGESTION: '/ingestion',
        UPLOAD: '/ingestion/upload',
    },
    health:{
        HEALTH: '/health',
    }
}

export default ApiObj
