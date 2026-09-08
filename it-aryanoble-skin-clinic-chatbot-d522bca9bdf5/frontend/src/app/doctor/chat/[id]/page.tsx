"use client"

import { RiRobot2Line, RiUser3Line, RiLoader4Line } from "@remixicon/react"
import { PromptInput } from "@/components/shared/prompt-input"
import { ChatEndSessionDialog } from "./components/chat-end-session-dialog"
import * as React from "react"
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller"
import { useParams } from "next/navigation"
import { useChatMessages, useSendMessage } from "../../hooks/use-doctor-chat"

export default function DoctorChatSessionPage() {
  const [showEndSession, setShowEndSession] = React.useState(false)
  
  const params = useParams();
  const sessionId = params.id as string;
  
  const { data: messages, isLoading } = useChatMessages(sessionId);
  const sendMessage = useSendMessage(sessionId);

  const handleSend = (text: string, category: string | undefined, files: File[]) => {
    if (!text.trim() && files.length === 0) return;

    const formData = new FormData();
    formData.append("role", "USER");
    formData.append("content", text || "Attached file(s)");
    files.forEach(f => formData.append("files", f));

    sendMessage.mutate(formData);
  };

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden w-full max-w-3xl mx-auto relative">
      {/* Chat Messages */}
      <MessageScrollerProvider>
        <MessageScroller className="flex-1 w-full px-4 bg-white">
          <MessageScrollerViewport>
            <MessageScrollerContent className="gap-6 py-6 w-full">
              {isLoading && (
                <div className="flex justify-center items-center py-10 text-zinc-500">
                  <RiLoader4Line className="size-6 animate-spin" />
                </div>
              )}
              
              {!isLoading && messages?.length === 0 && (
                <div className="text-center text-zinc-500 py-10">
                  <p>No messages yet.</p>
                </div>
              )}

              {!isLoading && messages?.map((msg) => {
                const isUser = msg.role === "USER";
                return (
                  <MessageScrollerItem key={msg.id}>
                    <div className={`flex items-start gap-3 mt-2 ${isUser ? 'flex-row-reverse' : ''}`}>
                      <div className="bg-zinc-100 rounded-md text-zinc-950 flex items-center justify-center p-1.5 mt-0.5 shrink-0">
                        {isUser ? <RiUser3Line className="size-4" /> : <RiRobot2Line className="size-4" />}
                      </div>
                      <div className={`${isUser ? 'bg-blue-500 text-white' : 'bg-blue-50 text-zinc-950'} p-3 rounded-md text-sm w-full leading-relaxed`}>
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                        
                        {msg.attachments && Object.keys(msg.attachments).length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {Object.keys(msg.attachments).map((filename) => (
                              <div key={filename} className={`px-2 py-1 text-xs rounded border ${isUser ? 'border-blue-400 bg-blue-600' : 'border-blue-200 bg-white'}`}>
                                📎 {filename}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </MessageScrollerItem>
                );
              })}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      {/* Chat Input */}
      <div className="p-4 bg-white shrink-0 mt-auto w-full z-10 border-t border-zinc-100 relative">
        {sendMessage.isPending && (
          <div className="absolute inset-0 z-10 bg-white/50 flex items-center justify-center rounded-md border-t border-zinc-100">
            <span className="text-sm text-zinc-500">Sending...</span>
          </div>
        )}
        <PromptInput 
          hideCategories 
          showAttachText 
          placeholder="Can you suggest a product for this condition..." 
          onSend={handleSend}
        />
      </div>

      <ChatEndSessionDialog 
        open={showEndSession} 
        onOpenChange={setShowEndSession}
      />
    </div>
  )
}
