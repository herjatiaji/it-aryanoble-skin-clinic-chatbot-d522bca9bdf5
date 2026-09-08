"use client"

import { RiRobot2Line, RiUser3Line, RiLoader4Line, RiArrowLeftLine } from "@remixicon/react"
import * as React from "react"
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller"
import { useParams, useRouter } from "next/navigation"
import { useChatMessages } from "@/app/doctor/hooks/use-doctor-chat"
import { Button } from "@/components/ui/button"

export default function ChatHistoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;
  
  const { data: messages, isLoading } = useChatMessages(sessionId);

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden w-full bg-white relative">
      {/* Header */}
      <div className="flex items-center gap-4 p-4 border-b border-gray-200 shrink-0">
        <Button variant="ghost" size="icon" onClick={() => router.back()} className="text-gray-500 hover:text-gray-900">
          <RiArrowLeftLine className="size-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Chat Session Details</h1>
          <p className="text-sm text-gray-500">Read-only view of the doctor&apos;s conversation</p>
        </div>
      </div>

      {/* Chat Messages */}
      <MessageScrollerProvider>
        <MessageScroller className="flex-1 w-full px-4 max-w-3xl mx-auto">
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
    </div>
  )
}
