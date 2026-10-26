"use client";

import { useChat } from "ai/react";
import ReactMarkdown from "react-markdown";

export function Chat() {
  const { messages, input, handleInputChange, handleSubmit } = useChat({ api: "/api/chat" });
  return (
    <div className="chat">
      {messages.map((m) => (
        <div key={m.id} className={m.role}>
          <ReactMarkdown>{m.content}</ReactMarkdown>
        </div>
      ))}
      <form onSubmit={handleSubmit}>
        <input value={input} onChange={handleInputChange} placeholder="Ask about your requests" />
      </form>
    </div>
  );
}
