import { useState, useCallback } from 'react';
import ApiObj from '../common/ApiObj';

interface StreamState {
  currentStage: string | null;
  toolCalls: string[];
  answerText: string;
  isStreaming: boolean;
  pausedReview: any | null;
}

export function useChatStream() {
  const [state, setState] = useState<StreamState>({
    currentStage: null,
    toolCalls: [],
    answerText: '',
    isStreaming: false,
    pausedReview: null,
  });

  const sendQuery = useCallback(async (query: string) => {
    setState({ currentStage: null, toolCalls: [], answerText: '', isStreaming: true, pausedReview: null });

    const response = await fetch(import.meta.env.VITE_BASE_URL + ApiObj.query.QUERY_STREAM, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem("accessToken")}`,
      },
      body: JSON.stringify({ query }),
    });
    // //console.log(response);
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    
    if (!reader) return;

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

        //console.log();
        

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const dataStr = line.slice(5).trim();
        
        if (dataStr === '[DONE]') {
          setState((prev) => ({ ...prev, isStreaming: false }));
          continue;
        }

        const parsed = JSON.parse(dataStr);
        // console.log(parsed.tool_call, parsed)
        if (parsed.node_name) {
            // console.log(parsed.node_name);
            
          setState((prev) => ({ ...prev, currentStage: parsed.node_name }));
          continue;
        }

        if (parsed.tool_call) {
            // console.log(parsed.tool_call)
          setState((prev) => ({ ...prev, toolCalls: [...prev.toolCalls, parsed.tool_call] }));
          continue;
        }

        if (parsed.token) {
            // console.log(parsed.token)
          setState((prev) => ({ ...prev, answerText: prev.answerText + parsed.token }));
          continue;
        }

        if (parsed.status === 'paused_for_review') {
          setState((prev) => ({ ...prev, pausedReview: parsed }));
          continue;
        }
      }
    }
  }, []);

  return { state, sendQuery };
}