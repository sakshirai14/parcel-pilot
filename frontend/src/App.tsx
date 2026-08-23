import React, { useState, useRef, useEffect } from 'react';
import { Send, Trash2, MessageSquare, Bot, AlertTriangle } from 'lucide-react';
import type { UserContext, ChatResponse, Citation, ToolActivity, ActionProposal, AuthorityResolution } from './types';
import { sendMessage, getBackendConfig } from './services/api';
import { ContextSwitcher } from './components/ContextSwitcher';
import { ConfirmationCard } from './components/ConfirmationCard';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  status?: string;
  citations?: Citation[];
  tools_used?: ToolActivity[];
  requires_confirmation?: boolean;
  proposed_action?: ActionProposal;
  authority_resolution?: AuthorityResolution;
}

const STARTER_QUESTIONS = [
  'Can Northstar cancel ORD-1001 without a cancellation fee?',
  'A pickup is three hours late because of carrier fault. Should I get a service credit?',
  'Is TKT-501 within SLA?',
];

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello! I am ParcelPilot AI. Ask me about B2B logistics operational data, SLA calculations, cancellation fees, or escalations.',
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [currentContext, setCurrentContext] = useState<UserContext>({
    role: 'CUSTOMER',
    customer_account_id: 'ACCT-001',
    user_id: 'customer-demo',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  const handleSend = async (textToSend: string) => {
    if (!textToSend.trim()) return;

    setErrorMessage(null);
    const userMsgId = Date.now().toString();
    const newUserMsg: Message = {
      id: userMsgId,
      sender: 'user',
      text: textToSend,
    };

    setMessages((prev) => [...prev, newUserMsg]);
    setInputText('');
    setIsLoading(true);

    try {
      const response: ChatResponse = await sendMessage(textToSend, currentContext.user_id || 'system-agent');
      
      // Map tools_used returned by API to ToolActivity
      const toolsActivity: ToolActivity[] = (response.tools_used || []).map((t) => ({
        tool: t.tool,
        status: t.status === 'completed' ? 'COMPLETED' : t.status === 'failed' ? 'FAILED' : 'RUNNING',
      }));

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: response.answer,
        status: response.status,
        citations: response.citations || [],
        tools_used: toolsActivity,
        requires_confirmation: response.requires_confirmation,
        proposed_action: response.proposed_action,
        authority_resolution: response.authority_resolution,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setErrorMessage(err.message || 'Something went wrong while contacting ParcelPilot. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(inputText);
    }
  };

  const clearConversation = () => {
    setMessages([
      {
        id: 'welcome',
        sender: 'assistant',
        text: 'Hello! I am ParcelPilot AI. Ask me about B2B logistics operational data, SLA calculations, cancellation fees, or escalations.',
      },
    ]);
    setErrorMessage(null);
  };



  const [backendConfig, setBackendConfig] = useState<{ llm_mode: string; llm_model: string } | null>(null);

  useEffect(() => {
    getBackendConfig()
      .then((config) => setBackendConfig(config))
      .catch((err) => console.error("Error loading backend config:", err));
  }, []);

  const isGeminiMode = backendConfig?.llm_mode?.toLowerCase() === 'gemini';

  return (
    <div className="app-container">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="navbar-logo">
          <Bot size={22} className="logo-icon" />
          <span className="logo-text">ParcelPilot AI Support</span>
        </div>
        <div className="navbar-meta">
          <div className="meta-context">
            <span className="meta-role-badge">{currentContext.role}</span>
            {currentContext.customer_account_id && (
              <span className="meta-account">{currentContext.customer_account_id}</span>
            )}
          </div>
          <div className={`meta-mode-badge ${isGeminiMode ? 'gemini' : 'mock'}`}>
            <span className="mode-dot">●</span>
            <span className="mode-text">{isGeminiMode ? 'GEMINI MODE' : 'MOCK MODE'}</span>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <main className="main-content">
        <aside className="sidebar">
          {/* Context Switcher */}
          <ContextSwitcher
            currentContext={currentContext}
            onContextChange={(ctx) => {
              setCurrentContext(ctx);
              clearConversation();
            }}
          />

          {/* Starter Questions */}
          <div className="starter-questions-panel">
            <h3 className="panel-title">Starter Prompts</h3>
            <div className="starter-questions-list">
              {STARTER_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(q)}
                  className="starter-question-btn"
                  disabled={isLoading}
                >
                  <MessageSquare size={12} />
                  <span>{q}</span>
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* Chat Window */}
        <section className="chat-window">
          {/* Chat Messages */}
          <div className="messages-area" role="log">
            {messages.map((msg) => {
              const isAssistant = msg.sender === 'assistant';

              return (
                <div
                  key={msg.id}
                  className={`message-bubble-wrapper ${isAssistant ? 'assistant' : 'user'}`}
                  data-testid={`message-${msg.sender}`}
                >
                  <div className="message-avatar">
                    {isAssistant ? <Bot size={18} /> : <span className="user-avatar-initial">U</span>}
                  </div>
                  <div className="message-content-wrapper">
                    <div className="message-text-bubble">
                      <p className="message-text">{msg.text}</p>
                      {msg.requires_confirmation && msg.proposed_action && (
                        <ConfirmationCard
                          proposal={msg.proposed_action}
                          userContext={currentContext}
                          onActionCompleted={(resultMessage, _isSuccess) => {
                            setMessages((prev) => [
                              ...prev,
                              {
                                id: Date.now().toString(),
                                sender: 'assistant',
                                text: resultMessage,
                              },
                            ]);
                          }}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="message-bubble-wrapper assistant loading-state" data-testid="loading-state">
                <div className="message-avatar">
                  <Bot size={18} />
                </div>
                <div className="message-content-wrapper">
                  <div className="loading-bubbles">
                    <span className="bubble-dot"></span>
                    <span className="bubble-dot"></span>
                    <span className="bubble-dot"></span>
                  </div>
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Footer Input Area */}
          <footer className="input-area">
            {errorMessage && (
              <div className="error-toast" data-testid="error-toast">
                <AlertTriangle size={14} />
                <span>{errorMessage}</span>
              </div>
            )}
            <div className="input-bar">
              <button
                onClick={clearConversation}
                className="clear-conversation-btn"
                title="Clear Conversation"
                disabled={isLoading}
              >
                <Trash2 size={16} />
              </button>
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask ParcelPilot anything..."
                rows={1}
                className="input-textarea"
                disabled={isLoading}
              />
              <button
                onClick={() => handleSend(inputText)}
                disabled={isLoading || !inputText.trim()}
                className="send-btn"
                aria-label="Send Message"
                title="Send Message"
              >
                <Send size={16} />
              </button>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}
