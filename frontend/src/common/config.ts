const API_BASE_URL = import.meta.env.VITE_BASE_URL||'';

export default {
    SUCCESS_CODE:[200, 201],
    auth:{
        LOGIN: `${API_BASE_URL}/auth/login`,
        REGISTER: `${API_BASE_URL}/auth/register`,
    },
    query:{
        QUERY: `${API_BASE_URL}/query`,
        QUERY_RESUME: `${API_BASE_URL}/query/resume`,
        QUERY_STREAM: `${API_BASE_URL}/query/stream`,
        QUERY_STREAM_RESUME: `${API_BASE_URL}/query/stream/resume`,
        QUERY_FLAG: `${API_BASE_URL}/query/flag`,
    },
    ingestion:{
        INGESTION: `${API_BASE_URL}/ingestion`,
    },
    health:{
        HEALTH: `${API_BASE_URL}/health`,
    }
}