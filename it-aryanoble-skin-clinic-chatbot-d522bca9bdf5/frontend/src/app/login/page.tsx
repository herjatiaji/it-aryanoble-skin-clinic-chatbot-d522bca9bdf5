"use client"

import { LoginForm } from "./components/login-form"

import Image from "next/image"

import { Suspense } from "react"

export default function LoginPage() {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xs">
            <Suspense fallback={<div className="text-center py-4">Loading...</div>}>
              <LoginForm />
            </Suspense>
          </div>
        </div>
      </div>
      <div className="relative hidden bg-muted lg:block">
        <Image
          src="/placeholder.svg"
          alt="Image"
          fill
          className="object-cover dark:brightness-[0.2] dark:grayscale"
        />
      </div>
    </div>
  )
}
