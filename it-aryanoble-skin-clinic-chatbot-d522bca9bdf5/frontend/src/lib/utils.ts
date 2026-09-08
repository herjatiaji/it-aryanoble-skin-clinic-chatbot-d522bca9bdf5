import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getErrorMessage(error: any, defaultMessage = "An error occurred. Please try again."): string {
  if (!error) return defaultMessage;
  
  const detail = error.response?.data?.detail;
  
  if (typeof detail === "string") {
    return detail;
  }
  
  if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) {
    return detail[0].msg;
  }
  
  return error.message || defaultMessage;
}
