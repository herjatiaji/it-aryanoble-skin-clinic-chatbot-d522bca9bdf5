import * as React from "react"
import { RiFilePdf2Line, RiCloseLine, RiFileList3Line } from "@remixicon/react"

interface ChatSummaryBubbleProps {
  summaryText: string
  file?: {
    name: string
    type: string
  }
}

export function ChatSummaryBubble({ summaryText, file }: ChatSummaryBubbleProps) {
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

      {/* Summary Card */}
      <div className="flex flex-col rounded-md overflow-hidden bg-orange-50 border border-orange-100/50">
        <div className="flex items-center gap-2 p-3 pb-0 text-orange-700">
          <RiFileList3Line className="size-5" />
          <span className="font-medium text-sm">Summary</span>
        </div>
        <div className="p-3 text-sm text-zinc-950 leading-relaxed whitespace-pre-line">
          {summaryText}
        </div>
      </div>
    </div>
  )
}
