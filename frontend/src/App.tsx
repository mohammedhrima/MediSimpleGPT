import { useState, useEffect, useRef, useCallback } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import './App.css';

const queryClient = new QueryClient();

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const MAX_QUERY_LENGTH = parseInt(import.meta.env.VITE_MAX_QUERY_LENGTH || '500');

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isTyping?: boolean;
  isError?: boolean;
}

const SUGGESTIONS = [
  'What is diabetes?',
  'How does the heart work?',
  'Explain hypertension simply',
  'What causes asthma?',
];

function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [clearFeedback, setClearFeedback] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const typingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [sessionId] = useState(() => {
    let id = localStorage.getItem('sessionId');
    if (!id) {
      id = `session_${Date.now()}`;
      localStorage.setItem('sessionId', id);
    }
    return id;
  });

  // Load conversation history on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await axios.get(`${API_BASE}/history/${sessionId}`);
        if (response.data.messages?.length) {
          setMessages(
            response.data.messages.map((msg: { role: 'user' | 'assistant'; content: string }) => ({
              role: msg.role,
              content: msg.content,
            }))
          );
        }
      } catch (err) {
        console.error('Error loading history:', err);
      }
    };
    loadHistory();

    // Auto-focus textarea
    textareaRef.current?.focus();

    // Cleanup typing interval on unmount
    return () => {
      if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    };
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    if (val.length > MAX_QUERY_LENGTH) return; // hard cap
    setInput(val);

    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  const clearConversation = useCallback(async () => {
    try {
      await axios.delete(`${API_BASE}/history/${sessionId}`);
      setMessages([]);
      setClearFeedback(true);
      setTimeout(() => setClearFeedback(false), 2000);
    } catch (err) {
      console.error('Error clearing conversation:', err);
    }
  }, [sessionId]);

  const typeMessage = useCallback((fullText: string) => {
    // Clear any existing typing interval
    if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);

    // Add placeholder message
    setMessages(prev => [...prev, { role: 'assistant', content: '', isTyping: true }]);

    let index = 0;
    typingIntervalRef.current = setInterval(() => {
      if (index < fullText.length) {
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant' && last.isTyping) {
            last.content = fullText.slice(0, index + 1);
          }
          return updated;
        });
        index++;
      } else {
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.isTyping) last.isTyping = false;
          return updated;
        });
        if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
      }
    }, 18);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const userMessage = text.trim();
      if (!userMessage || isLoading) return;

      setInput('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.focus();
      }

      // Handle clear commands
      const lower = userMessage.toLowerCase();
      if (
        lower === 'clear' ||
        lower.includes('clear conversation') ||
        lower.includes('delete conversation') ||
        lower.includes('reset conversation')
      ) {
        await clearConversation();
        return;
      }

      setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
      setIsLoading(true);

      try {
        const response = await axios.post(`${API_BASE}/chat`, {
          query: userMessage,
          session_id: sessionId,
        });

        const reply: string = response.data.response;

        if (!reply) throw new Error('Empty response from server');

        typeMessage(reply);
      } catch (err) {
        console.error('Chat error:', err);
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: 'Sorry, something went wrong. Please try again.',
            isError: true,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, sessionId, clearConversation, typeMessage]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const charsLeft = MAX_QUERY_LENGTH - input.length;
  const isNearLimit = charsLeft <= 80;

  return (
    <div className="chat-container">
      <header className="chat-header">
        <div className="header-inner">
          <div className="header-brand">
            <span className="brand-icon">⚕</span>
            <h1>MediSimple</h1>
          </div>
          <button
            className="clear-btn"
            onClick={clearConversation}
            title="Clear conversation"
            // disabled={messages.length === 0}
          >
            {clearFeedback ? '✓ Cleared' : 'Clear chat'}
          </button>
        </div>
      </header>
      <div className='chat-section'>
      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🩺</div>
            <h2>How can I help you today?</h2>
            <p>
              Ask me anything about medical topics. I'll search Wikipedia and give you a simple,
              friendly explanation.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map(s => (
                <button key={s} className="suggestion-pill" onClick={() => sendMessage(s)}>
                  {s}
                </button>
              ))}
            </div>
            <p className="clear-hint">
              Tip: type <code>clear</code> anytime to reset the conversation.
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div key={i} className={`message ${msg.role} ${msg.isError ? 'error' : ''}`}>
                <div className="message-content">
                  <div className={`avatar ${msg.role}`}>{msg.role === 'user' ? 'U' : '⚕'}</div>
                  <div className="text">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              </div>
            ))}

            {/* Thinking dots — only show when loading AND last message is from user */}
            {isLoading && messages[messages.length - 1]?.role === 'user' && (
              <div className="message assistant">
                <div className="message-content">
                  <div className="avatar assistant">⚕</div>
                  <div className="loading">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className="input-container">
        <div className="input-wrapper">
          <form className="input-form" onSubmit={handleSubmit}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask about a medical topic…"
              rows={1}
              disabled={isLoading}
            />
            <button type="submit" className="send-button" disabled={!input.trim() || isLoading}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </button>
          </form>
          {isNearLimit && (
            <div className={`char-count ${charsLeft <= 20 ? 'danger' : ''}`}>
              {charsLeft} characters left
            </div>
          )}
        </div>
      </div>
      </div>

    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ChatInterface />
    </QueryClientProvider>
  );
}