import * as React from "react"
import { RiFilePdf2Line, RiCloseLine, RiErrorWarningLine } from "@remixicon/react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

interface ChatOutOfScopeBubbleProps {
  message?: string
  doctor?: {
    name: string
    role: string
    knowledgeBase: string[]
  }
  file?: {
    name: string
    type: string
  }
}

export function ChatOutOfScopeBubble({ 
  message = "Sorry, the knowledge you are looking for cannot be provided because it is outside your scope.",
  doctor = {
    name: "Dr. Vivian Lumina",
    role: "Doctor",
    knowledgeBase: ["Acne Care", "Anti Aging", "Dark Spot"]
  },
  file 
}: ChatOutOfScopeBubbleProps) {
  return (
    <div className="flex flex-col gap-2 w-full mt-2">
      {/* Attachment Badge */}
      {file && (
        <div className="flex items-center gap-2 px-2 py-2 rounded-md border border-black/10 bg-white w-fit">
          <div className="bg-red-100 p-1.5 rounded text-red-900 flex items-center justify-center">
            <RiFilePdf2Line className="size-4" />
          </div>
          <div className="flex flex-col justify-center">
            <span className="text-xs font-medium text-zinc-950 truncate max-w-35">{file.name}</span>
            <span className="text-[10px] text-zinc-500">{file.type}</span>
          </div>
          <button type="button" className="text-zinc-400 hover:text-zinc-600 ml-1">
            <RiCloseLine className="size-4" />
          </button>
        </div>
      )}

      {/* Warning Card */}
      <div className="flex flex-col rounded-md overflow-hidden bg-orange-50 border border-orange-100/50">
        <div className="flex items-center gap-2 p-3 pb-0 text-orange-700">
          <RiErrorWarningLine className="size-5" />
          <span className="font-medium text-sm">Out of Scope Knowledge</span>
        </div>
        
        <div className="px-3 pt-2 pb-4 text-sm text-zinc-950 leading-relaxed whitespace-pre-line">
          {message}
        </div>
        
        {/* Doctor Card Profile */}
        <div className="mx-3 mb-3 p-4 bg-white rounded-xl shadow-sm border border-black/5 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <Avatar className="size-10 rounded-lg">
              <AvatarImage src="" alt={doctor.name} />
              <AvatarFallback className="rounded-lg bg-zinc-100 text-zinc-600 text-sm font-medium">
                {doctor.name.substring(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-zinc-950">{doctor.name}</span>
              <span className="text-[13px] text-zinc-500">{doctor.role}</span>
            </div>
          </div>
          
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-zinc-500">Knowledge Base</span>
            <div className="flex flex-wrap gap-2">
              {doctor.knowledgeBase.map((kb, idx) => (
                <div 
                  key={idx} 
                  className="bg-zinc-100/80 text-zinc-900 text-[13px] font-medium px-2.5 py-1 rounded-md"
                >
                  {kb}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
