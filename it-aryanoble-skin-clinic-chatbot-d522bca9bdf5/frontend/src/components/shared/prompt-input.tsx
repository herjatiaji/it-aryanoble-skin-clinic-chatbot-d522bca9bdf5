"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  RiFilePdfLine,
  RiCloseLine,
  RiAttachmentLine,
  RiMedicineBottleLine,
  RiSyringeLine,
  RiMegaphoneLine,
  RiCornerDownLeftLine,
  RiArchiveLine
} from "@remixicon/react"
import {
  Attachment,
  AttachmentMedia,
  AttachmentContent,
  AttachmentTitle,
  AttachmentDescription,
  AttachmentActions,
  AttachmentAction,
} from "@/components/ui/attachment"

export interface PromptInputProps extends React.HTMLAttributes<HTMLDivElement> {
  onSend?: (value: string, category: string | undefined, files: File[]) => boolean | void
  hideCategories?: boolean
  showAttachText?: boolean
  placeholder?: string
  minRows?: number
  disabled?: boolean
}

export function PromptInput({ className, onSend, hideCategories, showAttachText, placeholder, minRows = 1, disabled, ...props }: PromptInputProps) {
  const [activeCategory, setActiveCategory] = React.useState<"Product" | "Treatment" | "Promotional" | "Other" | undefined>()
  const [categoryError, setCategoryError] = React.useState(false)
  const [inputValue, setInputValue] = React.useState("")
  const [attachedFiles, setAttachedFiles] = React.useState<File[]>([])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      setAttachedFiles((prev) => [...prev, ...Array.from(files)])
    }
  }

  const removeFile = (indexToRemove: number) => {
    setAttachedFiles((prev) => prev.filter((_, index) => index !== indexToRemove))
  }

  const handleSend = () => {
    const success = onSend?.(inputValue, activeCategory, attachedFiles)
    if (success === false) {
      if (!activeCategory && !hideCategories) {
        setCategoryError(true)
      }
    } else {
      setInputValue("")
      setAttachedFiles([])
      setActiveCategory(undefined)
      setCategoryError(false)
    }
  }

  return (
    <div className={cn("w-full bg-zinc-100/50 rounded-md p-2.5", className)} {...props}>
      {/* Attached Files Preview */}
      {attachedFiles.length > 0 && (
        <div className="flex gap-2 mb-2 overflow-x-auto pb-2 custom-scrollbar">
          {attachedFiles.map((file, idx) => (
            <Attachment key={idx} className="bg-white border-border shadow-sm p-1.5 min-w-35 max-w-50 shrink-0">
              <AttachmentMedia className="bg-blue-50 text-blue-600">
                <RiFilePdfLine className="w-5 h-5" />
              </AttachmentMedia>
              <AttachmentContent className="overflow-hidden">
                <AttachmentTitle className="text-[13px] font-medium text-zinc-950 truncate">{file.name}</AttachmentTitle>
                <AttachmentDescription className="text-[11px] text-zinc-500">{(file.size / 1024).toFixed(1)} KB</AttachmentDescription>
              </AttachmentContent>
              <AttachmentActions>
                <AttachmentAction 
                  variant="ghost" 
                  className="hover:bg-zinc-100 text-zinc-500 hover:text-zinc-950 ml-1"
                  onClick={() => removeFile(idx)}
                >
                  <RiCloseLine className="w-4 h-4" />
                </AttachmentAction>
              </AttachmentActions>
            </Attachment>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="mb-2">
        <textarea
          rows={minRows}
          disabled={disabled}
          className="w-full bg-transparent resize-none outline-none border-none text-sm text-zinc-950 placeholder:text-zinc-500 overflow-y-auto max-h-32 custom-scrollbar disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder={disabled ? "AI Assistant access is disabled..." : placeholder || "Describe what you want to describe the knowledge is about..."}
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = e.target.scrollHeight + 'px'
          }}
        />
      </div>

      {/* Actions Area */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Attach Button */}
          <label 
            htmlFor={disabled ? undefined : "file-upload"} 
            className={cn(
              "flex items-center justify-center rounded-md border border-border bg-white text-zinc-700 transition-colors",
              disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700",
              showAttachText ? "py-1.5 px-2.5 gap-1.5" : "aspect-square p-1.5"
            )} 
            title={disabled ? "Access disabled" : "Attach file"}
          >
            <input 
              id="file-upload"
              type="file" 
              disabled={disabled}
              className="sr-only" 
              onChange={handleFileChange}
              onClick={(e) => {
                (e.target as HTMLInputElement).value = '';
              }}
              multiple
            />
            <RiAttachmentLine className="size-4 pointer-events-none shrink-0" />
            {showAttachText && <span className="text-xs font-medium pointer-events-none">Attach file</span>}
          </label>
          
          {/* Categories */}
          {!hideCategories && (
            <>
              <button
                type="button"
                disabled={disabled}
                onClick={() => { setActiveCategory("Product"); setCategoryError(false); }}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
                  activeCategory === "Product" 
                    ? "border-blue-500 bg-blue-50 text-blue-700" 
                    : categoryError
                      ? "border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100"
                      : "border-border bg-white text-zinc-700 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700"
                )}
              >
                <RiMedicineBottleLine className="size-3.5" />
                <span>Product</span>
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => { setActiveCategory("Treatment"); setCategoryError(false); }}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
                  activeCategory === "Treatment" 
                    ? "border-blue-500 bg-blue-50 text-blue-700" 
                    : categoryError
                      ? "border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100"
                      : "border-border bg-white text-zinc-700 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700"
                )}
              >
                <RiSyringeLine className="size-3.5" />
                <span>Treatment</span>
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => { setActiveCategory("Promotional"); setCategoryError(false); }}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
                  activeCategory === "Promotional" 
                    ? "border-blue-500 bg-blue-50 text-blue-700" 
                    : categoryError
                      ? "border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100"
                      : "border-border bg-white text-zinc-700 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700"
                )}
              >
                <RiMegaphoneLine className="size-3.5" />
                <span>Promotional</span>
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => { setActiveCategory("Other"); setCategoryError(false); }}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
                  activeCategory === "Other" 
                    ? "border-blue-500 bg-blue-50 text-blue-700" 
                    : categoryError
                      ? "border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100"
                      : "border-border bg-white text-zinc-700 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700"
                )}
              >
                <RiArchiveLine className="size-3.5" />
                <span>Other</span>
              </button>
            </>
          )}
        </div>
        
        {/* Send Button */}
        <Button 
          size="icon" 
          disabled={disabled || (!inputValue.trim() && attachedFiles.length === 0)}
          className="h-8 w-8 bg-blue-500 hover:bg-blue-600 rounded-md shrink-0 text-white disabled:opacity-50"
          onClick={handleSend}
        >
          <RiCornerDownLeftLine className="size-5" />
        </Button>
      </div>
    </div>
  )
}
