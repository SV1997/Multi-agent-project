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

  const sendQuery = useCallback(async (query: string, sessionId: string, turnId: string) => {
    setState({ currentStage: null, toolCalls: [], answerText: '', isStreaming: true, pausedReview: null });

    const response = await fetch(import.meta.env.VITE_BASE_URL + ApiObj.query.QUERY_STREAM, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem("accessToken")}`,
      },
      body: JSON.stringify({ query, sessionId, turnId }),
    });
    // //console.log(response);
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    
    if (!reader) return;

    let buffer = '';
    let sawDone = false;

    const processLine = (line: string) => {
      if (!line.startsWith('data:')) return;
      const dataStr = line.slice(5).trim();
      if (!dataStr) return;

      if (dataStr === '[DONE]') {
        sawDone = true;
        setState((prev) => ({ ...prev, isStreaming: false }));
        return;
      }

      let parsed: any;
      try {
        parsed = JSON.parse(dataStr);
      } catch {
        return;
      }
      console.log(parsed);
      
      if (parsed.node_name) {
        setState((prev) => ({ ...prev, currentStage: parsed.node_name }));
        return;
      }

      if (parsed.tool_call) {
        setState((prev) => ({ ...prev, toolCalls: [...prev.toolCalls, parsed.tool_call] }));
        return;
      }

      if (parsed.token) {
        setState((prev) => ({ ...prev, answerText: prev.answerText + parsed.token }));
        return;
      }
        

      if (parsed.status === 'paused_for_review') {
        console.log(parsed.status, parsed.status === 'paused_for_review');
        setState((prev) => ({ ...prev, pausedReview: parsed }));
        return;
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }
      }

      // Flush whatever is left in the buffer (e.g. a final event whose
      // trailing "\n\n" got split across reads, or arrived without one).
      buffer += decoder.decode();
      for (const line of buffer.split('\n\n')) {
        processLine(line);
      }
    } finally {
      // Safety net: if the stream ended (or errored) without an explicit
      // [DONE] marker, don't leave the UI stuck mid-flight.
      if (!sawDone) {
        setState((prev) => ({ ...prev, isStreaming: false }));
      }
    }
  }, []);

  return { state, sendQuery };
}