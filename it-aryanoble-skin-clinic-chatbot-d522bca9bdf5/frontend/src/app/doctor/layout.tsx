"use client"

import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { DoctorSidebar } from "@/components/layout/DoctorSidebar"
import { RiArrowLeftLine } from "@remixicon/react"
import { useRouter } from "next/navigation"

import { RouteGuard } from "@/components/auth/route-guard"

export default function DoctorLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()

  return (
    <RouteGuard allowedTypes={["DOCTOR"]}>
      <div className="flex flex-col h-screen overflow-hidden">
        <header className="fixed top-0 left-0 w-full flex items-center border-b px-4 h-12 bg-white z-20">
          <button onClick={() => router.push("/widget-demo")} className="flex items-center text-zinc-950 hover:text-blue-500 transition-colors">
            <div className="flex items-center justify-center mr-2">
              <RiArrowLeftLine className="size-4" />
            </div>
            <span className="font-semibold text-sm">ERHA Medical Assistant</span>
          </button>
        </header>
        
        <div className="flex-1 pt-12 overflow-hidden relative">
          <SidebarProvider className="h-full" style={{ minHeight: 0 }}>
            <DoctorSidebar className="top-12! h-[calc(100svh-48px)]!" />
            <SidebarInset className="bg-white h-full" style={{ minHeight: 0 }}>
              <div className="flex-1 overflow-auto relative h-full">
                {children}
              </div>
            </SidebarInset>
          </SidebarProvider>
        </div>
      </div>
    </RouteGuard>
  )
}
