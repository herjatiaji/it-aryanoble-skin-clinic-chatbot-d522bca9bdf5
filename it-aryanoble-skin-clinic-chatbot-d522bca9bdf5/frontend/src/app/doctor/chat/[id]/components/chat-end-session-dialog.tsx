"use client"

import * as React from "react"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { RiThumbUpLine, RiThumbDownLine, RiTimeLine } from "@remixicon/react"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

interface ChatEndSessionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onFeedbackSubmit?: (rate: "good" | "bad", feedback: string) => void
}

export function ChatEndSessionDialog({ open, onOpenChange, onFeedbackSubmit }: ChatEndSessionDialogProps) {
  const [rate, setRate] = React.useState<"good" | "bad" | null>(null)
  const [feedback, setFeedback] = React.useState("")
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  const handleSubmit = () => {
    setIsSubmitting(true)
    // Simulate API call
    setTimeout(() => {
      setIsSubmitting(false)
      onFeedbackSubmit?.(rate || "good", feedback)
      onOpenChange(false)
    }, 1500)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-100 p-0 gap-0 border-none bg-white rounded-md overflow-hidden shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <DialogTitle className="text-base font-semibold text-zinc-950">
            Session Ended
          </DialogTitle>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col gap-6">
          <div className="flex flex-col items-center gap-4">
            <div className="flex items-center justify-center size-12 rounded-md bg-blue-50 text-blue-600">
              <RiTimeLine className="size-6" />
            </div>
            <p className="text-sm text-zinc-500 text-center leading-relaxed">
              You have reached the 5-minute limit for this session, please give this session a feedback so we can improve, and you will get a summary.
            </p>
          </div>

          {/* Rate */}
          <div className="flex flex-col gap-2">
            <label className="text-sm text-zinc-950 font-medium">Rate</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setRate("good")}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border",
                  rate === "good"
                    ? "border-blue-500 bg-blue-50 text-blue-500"
                    : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
                )}
              >
                <RiThumbUpLine className="size-4" />
                Good
              </button>
              <button
                type="button"
                onClick={() => setRate("bad")}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border",
                  rate === "bad"
                    ? "border-red-500 bg-red-50 text-red-500"
                    : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
                )}
              >
                <RiThumbDownLine className="size-4" />
                Bad
              </button>
            </div>
          </div>

          {/* Feedback */}
          <div className="flex flex-col gap-2">
            <label className="text-sm text-zinc-950 font-medium">Feedback</label>
            <Textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Type your feedback here..."
              className="resize-none h-24 text-sm text-zinc-700 border-zinc-200 focus-visible:ring-blue-500"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 pt-0">
          <Button className="w-full bg-blue-500 hover:bg-blue-600 text-white font-medium"
            onClick={handleSubmit}
            disabled={isSubmitting || !rate}
          >
            {isSubmitting ? (
              <>
                <Spinner className="mr-2 size-4 text-white" />
                Generating Summary
              </>
            ) : (
              "Get Summary"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
