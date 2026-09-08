"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { RiArrowRightUpLine, RiCloseLine, RiRobot2Line } from "@remixicon/react"
import { PromptInput } from "@/components/shared/prompt-input"
import { cn } from "@/lib/utils"
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller"

export function FloatingChatWidget() {
  const pathname = usePathname()
  const router = useRouter()
  const [isClosed, setIsClosed] = React.useState(false)

  // Hide on full-page chat
  if (pathname?.startsWith("/doctor/chat/")) {
    return null
  }

  const handleMaximize = () => {
    router.push("/doctor/chat/1")
  }

  return (
    <>
      {/* Minimized Button */}
      <button
        type="button"
        onClick={() => setIsClosed(false)}
        className={cn(
          "fixed bottom-6 right-6 z-50 flex items-center justify-center size-14 bg-blue-500 text-white rounded-md shadow-lg hover:bg-blue-600 transition-all duration-300 ease-out",
          isClosed 
            ? "opacity-100 translate-y-0" 
            : "opacity-0 translate-y-12 pointer-events-none"
        )}
        aria-label="Open AI Assistant"
      >
        <RiRobot2Line className="size-6" />
      </button>

      {/* Expanded Widget */}
      <div 
        className={cn(
          "fixed bottom-6 right-6 w-100 h-140 bg-white rounded-xl shadow-[0_8px_30px_rgb(0,0,0,0.12)] overflow-hidden flex flex-col z-50 border border-zinc-200 transition-all duration-300 ease-out",
          isClosed 
            ? "opacity-0 translate-y-12 pointer-events-none" 
            : "opacity-100 translate-y-0"
        )}
      >
      {/* Header (h:65px) */}
      <div className="bg-blue-500 h-16.25 px-4 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center size-10 bg-white/10 rounded-lg text-white">
            <RiRobot2Line className="size-5" />
          </div>
          <div className="flex flex-col">
            <span className="text-white font-semibold text-sm leading-tight">Erha AI</span>
            <span className="text-white/80 text-xs">Your artificial intelligence assistant</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button 
            type="button" 
            onClick={handleMaximize}
            className="text-white/80 hover:text-white p-1.5 hover:bg-white/10 rounded-md transition-colors"
          >
            <RiArrowRightUpLine className="size-5" />
          </button>
          <button 
            type="button" 
            onClick={() => setIsClosed(true)}
            className="text-white/80 hover:text-white p-1.5 hover:bg-white/10 rounded-md transition-colors"
          >
            <RiCloseLine className="size-5" />
          </button>
        </div>
      </div>

      {/* Content Area (h:375px) */}
      <MessageScrollerProvider>
        <MessageScroller className="flex-1 bg-white">
          <MessageScrollerViewport className="p-4">
            <MessageScrollerContent className="gap-4">
              <MessageScrollerItem>
                <div className="bg-blue-50 rounded-lg p-3 text-sm text-zinc-950 self-start max-w-[85%]">
                  Your artificial intelligence assistant
                </div>
              </MessageScrollerItem>
              <MessageScrollerItem>
                <div className="flex w-full justify-end">
                  <div className="bg-zinc-100 rounded-lg p-3 text-sm text-zinc-950 self-end max-w-[85%]">
                    Can you help me check the side effects of Retinol 1%?
                  </div>
                </div>
              </MessageScrollerItem>
              <MessageScrollerItem>
                <div className="bg-blue-50 rounded-lg p-3 text-sm text-zinc-950 self-start max-w-[85%]">
                  Retinol 1% is a strong retinoid. Common side effects include redness, peeling, dryness, and mild irritation, especially during the first few weeks of use (often called &quot;retinization&quot;). I recommend starting slowly, applying it 2-3 times a week, and always following up with a good moisturizer and daily sunscreen.
                </div>
              </MessageScrollerItem>
              <MessageScrollerItem>
                <div className="flex w-full justify-end">
                  <div className="bg-zinc-100 rounded-lg p-3 text-sm text-zinc-950 self-end max-w-[85%]">
                    What if the patient has sensitive skin?
                  </div>
                </div>
              </MessageScrollerItem>
              <MessageScrollerItem>
                <div className="bg-blue-50 rounded-lg p-3 text-sm text-zinc-950 self-start max-w-[85%]">
                  For sensitive skin, a 1% concentration might be too harsh. You might want to recommend the &quot;sandwich method&quot; (moisturizer, retinol, moisturizer) or step down to a lower concentration like 0.3% or 0.5% to build tolerance first.
                </div>
              </MessageScrollerItem>
              <MessageScrollerItem scrollAnchor>
                <div className="flex w-full justify-end">
                  <div className="bg-zinc-100 rounded-lg p-3 text-sm text-zinc-950 self-end max-w-[85%]">
                    Great, I&apos;ll recommend the sandwich method for now. Thanks!
                  </div>
                </div>
              </MessageScrollerItem>
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      {/* Input Area (h:120px) */}
      <div className="p-3 bg-white border-t border-zinc-100 shrink-0">
        <PromptInput 
          hideCategories={true} 
          showAttachText={true} 
          placeholder="Describe what your concern is..."
        />
      </div>
    </div>
    </>
  )
}
