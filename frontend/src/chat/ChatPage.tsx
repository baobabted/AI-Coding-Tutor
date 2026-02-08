import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../api/http";
import { ChatMessage, ChatSession } from "../api/types";
import { createChatSocket, WsEvent } from "../api/ws";
import { ChatMessageList } from "./ChatMessageList";
import { ChatInput } from "./ChatInput";
import { ChatSidebar } from "./ChatSidebar";

export function ChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<ReturnType<typeof createChatSocket> | null>(null);

  // Sidebar state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Load sessions on mount
  useEffect(() => {
    apiFetch<ChatSession[]>("/api/chat/sessions")
      .then(setSessions)
      .catch(() => {});
  }, []);

  const handleEvent = useCallback((event: WsEvent) => {
    switch (event.type) {
      case "session":
        setSessionId((prev) => {
          if (prev !== event.session_id) {
            // Refresh the session list when a new session is created
            apiFetch<ChatSession[]>("/api/chat/sessions")
              .then(setSessions)
              .catch(() => {});
          }
          return event.session_id;
        });
        break;
      case "token":
        setStreamingContent((prev) => prev + event.content);
        break;
      case "done":
        setStreamingContent((prev) => {
          if (prev) {
            setMessages((msgs) => [
              ...msgs,
              { role: "assistant", content: prev },
            ]);
          }
          return "";
        });
        setIsStreaming(false);
        break;
      case "canned":
        setMessages((msgs) => [
          ...msgs,
          { role: "assistant", content: event.content },
        ]);
        setIsStreaming(false);
        break;
      case "error":
        setMessages((msgs) => [
          ...msgs,
          { role: "assistant", content: `Error: ${event.message}` },
        ]);
        setStreamingContent("");
        setIsStreaming(false);
        break;
    }
  }, []);

  useEffect(() => {
    const socket = createChatSocket(
      handleEvent,
      () => setConnected(true),
      () => setConnected(false)
    );
    socketRef.current = socket;

    return () => {
      socket.close();
    };
  }, [handleEvent]);

  const handleSend = (content: string) => {
    if (!socketRef.current || isStreaming) return;

    setMessages((msgs) => [...msgs, { role: "user", content }]);
    setStreamingContent("");
    setIsStreaming(true);
    socketRef.current.send(content, sessionId);
  };

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) return;
    try {
      const msgs = await apiFetch<ChatMessage[]>(
        `/api/chat/sessions/${id}/messages`
      );
      setMessages(msgs);
      setSessionId(id);
      setStreamingContent("");
    } catch {
      // Session may have been deleted
    }
  };

  const handleNewChat = () => {
    setSessionId(null);
    setMessages([]);
    setStreamingContent("");
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await apiFetch(`/api/chat/sessions/${id}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (id === sessionId) {
        setSessionId(null);
        setMessages([]);
        setStreamingContent("");
      }
    } catch {
      // Ignore errors
    }
  };

  const greeting = user
    ? `Hello ${user.username}! I am your AI coding tutor. Ask me a question about programming, mathematics, or physics and I will guide you through it.`
    : "";

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <ChatSidebar
        sessions={sessions}
        activeSessionId={sessionId}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages area */}
        <div className="flex-1 overflow-hidden flex flex-col min-h-0 bg-gray-50">
          {messages.length === 0 && !streamingContent ? (
            <div className="flex-1 flex items-center justify-center px-4">
              <div className="text-center max-w-md">
                <h2 className="text-2xl font-bold text-brand mb-3">
                  Guided Cursor
                </h2>
                <p className="text-gray-600">{greeting}</p>
              </div>
            </div>
          ) : (
            <ChatMessageList
              messages={messages}
              streamingContent={streamingContent}
            />
          )}
        </div>

        {/* Input area */}
        <ChatInput onSend={handleSend} disabled={isStreaming || !connected} />

        {/* Disclaimer */}
        <div className="text-center text-xs text-gray-400 py-1.5 bg-white border-t border-gray-100">
          AI responses may contain errors. Always verify important information independently.
        </div>
      </div>
    </div>
  );
}
