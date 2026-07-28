const ApiObj = {
    auth:{
        LOGIN: '/auth/login',
        REGISTER: '/auth/register',
    },
    query:{
        QUERY: '/query',
        QUERY_RESUME: '/query/resume',
        QUERY_STREAM: '/query/stream',
        QUERY_STREAM_RESUME: '/query/stream/resume',
        QUERY_FLAG: '/query/flag',
    },
    session:{
        SESSION_CREATE: '/session/create',
        SESSION_LIST: '/session/list',
        SESSION_MESSAGES: (id: string) => `/session/${id}/messages`,
    },
    ingestion:{
        INGESTION: '/ingestion',
    },
    health:{
        HEALTH: '/health',
    }
}

export default ApiObj
