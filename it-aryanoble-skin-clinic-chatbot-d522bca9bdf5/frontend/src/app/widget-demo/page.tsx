import { FloatingChatWidget } from "@/components/shared/floating-chat-widget"

export default function WidgetDemoPage() {
  return (
    <div className="min-h-screen bg-zinc-100 flex flex-col items-center justify-center p-8">
      <div className="text-center max-w-lg mb-8">
        <h1 className="text-2xl font-bold text-zinc-900 mb-2">External CIS Dashboard (Mock)</h1>
      </div>
      
      {/* injected globally or via an embed script in the external system.
      */}
      <FloatingChatWidget />
    </div>
  )
}
