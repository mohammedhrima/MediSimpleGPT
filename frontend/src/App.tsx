import { useState, useEffect, useRef } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios from 'axios';
import './App.css';

const queryClient = new QueryClient();

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isTyping?: boolean;
}

function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => {
    // Get or create persistent session ID
    let id = localStorage.getItem('sessionId');
    if (!id) {
      id = `session_${Date.now()}`;
      localStorage.setItem('sessionId', id);
    }
    return id;
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load conversation history on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await axios.get(`http://127.0.0.1:8000/history/${sessionId}`);
        if (response.data.messages) {
          setMessages(response.data.messages.map((msg: any) => ({
            role: msg.role,
            content: msg.content
          })));
        }
      } catch (error) {
        console.error('Error loading history:', error);
      }
    };
    loadHistory();
  }, [sessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    
    // Check for clear command
    if (userMessage.toLowerCase().includes('clear conversation') || 
        userMessage.toLowerCase().includes('delete conversation') ||
        userMessage.toLowerCase().includes('reset conversation')) {
      try {
        await axios.delete(`http://127.0.0.1:8000/history/${sessionId}`);
        setMessages([]);
        return;
      } catch (error) {
        console.error('Error clearing conversation:', error);
      }
    }
    
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      // Call backend to process query
      const response = await axios.post('http://127.0.0.1:8000/chat', {
        query: userMessage,
        session_id: sessionId,
        history: messages
      });

      const assistantMessage = response.data.response;
      
      // Add assistant message with typing effect
      setMessages(prev => [...prev, { role: 'assistant', content: '', isTyping: true }]);
      
      // Simulate typing
      let index = 0;
      const typingInterval = setInterval(() => {
        if (index < assistantMessage.length) {
          setMessages(prev => {
            const newMessages = [...prev];
            const lastMessage = newMessages[newMessages.length - 1];
            lastMessage.content = assistantMessage.slice(0, index + 1);
            return newMessages;
          });
          index++;
        } else {
          setMessages(prev => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1].isTyping = false;
            return newMessages;
          });
          clearInterval(typingInterval);
        }
      }, 20);

    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error. Please try again.' 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h1>Medical Information Assistant</h1>
      </div>

      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <h2>How can I help you today?</h2>
            <p>Ask me anything about medical topics. I'll search Wikipedia and provide simplified explanations.</p>
          </div>
        ) : (
          <>
            {messages.map((message, index) => (
              <div key={index} className={`message ${message.role}`}>
                <div className="message-content">
                  <div className={`avatar ${message.role}`}>
                    {message.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div className="text">
                    {message.content}
                    {message.isTyping && <span className="cursor"></span>}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && messages[messages.length - 1]?.role === 'user' && (
              <div className="message assistant">
                <div className="message-content">
                  <div className="avatar assistant">AI</div>
                  <div className="loading">
                    <span></span>
                    <span></span>
                    <span></span>
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
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search for articles about diabetes..."
              rows={1}
              disabled={isLoading}
            />
            <button 
              type="submit" 
              className="send-button"
              disabled={!input.trim() || isLoading}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </button>
          </form>
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
