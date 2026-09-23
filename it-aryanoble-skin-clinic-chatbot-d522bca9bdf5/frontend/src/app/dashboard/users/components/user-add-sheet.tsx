import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field, FieldLabel, FieldTitle, FieldContent } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { RiEyeLine, RiEyeOffLine, RiImageAddLine, RiAddLine, RiLoader4Line } from "@remixicon/react"
import { useState, useEffect } from "react"
import { useCreateStaff } from "../hooks/use-users"
import { useRoles } from "../hooks/use-roles"

export function UserAddSheet({
  isOpen,
  onOpenChange,
}: {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  
  const createStaff = useCreateStaff()
  const { data: roles = [] } = useRoles()

  useEffect(() => {
    if (!isOpen) {
      setTimeout(() => {
        // Reset state when sheet closes
        setName("")
        setEmail("")
        setPassword("")
        setRole("")
        setShowPassword(false)
      }, 0)
    }
  }, [isOpen])

  const handleAddUser = () => {
    if (!name || !email) return;
    
    createStaff.mutate({
      name,
      email,
      password: password || "password123",
      roles: role ? [role] : ["Staff"],
    }, {
      onSuccess: () => onOpenChange(false)
    })
  }

  return (
    <Sheet open={isOpen} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-md p-0 flex flex-col h-full bg-white">
        <SheetHeader className="p-4 border-b h-15 flex justify-center">
          <SheetTitle className="text-base font-semibold text-gray-900 flex justify-between items-center w-full">
            Add New User
          </SheetTitle>
        </SheetHeader>
        
        <div className="p-4 flex-1 overflow-y-auto">
          <div className="flex flex-col gap-6">
            <Field>
              <FieldLabel>
                <FieldTitle>Profile Picture</FieldTitle>
              </FieldLabel>
              <FieldContent>
                <div className="border border-gray-200 rounded-md p-4 flex flex-col items-center justify-center text-center">
                  <div className="h-8 w-8 mb-2 flex items-center justify-center text-zinc-500">
                    <RiImageAddLine className="h-5 w-5" />
                  </div>
                  <div className="flex gap-1 text-sm">
                    <span className="font-medium text-gray-900">Drag & Drop or</span>
                    <span className="font-medium text-blue-700 cursor-pointer">Choose File</span>
                  </div>
                  <p className="text-xs text-zinc-600 mt-1">Maximum file size: 5 MB</p>
                  <p className="text-xs text-zinc-600">Format file: .jpg, .jpeg, .png</p>
                </div>
              </FieldContent>
            </Field>

            <Field>
              <FieldLabel>
                <FieldTitle>Name</FieldTitle>
              </FieldLabel>
              <FieldContent>
                <div className="relative">
                  <Input 
                    id="name" 
                    placeholder="John Doe" 
                    className="border-gray-200 bg-white focus-visible:ring-blue-500" 
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
              </FieldContent>
            </Field>

            <Field>
              <FieldLabel>
                <FieldTitle>Role</FieldTitle>
              </FieldLabel>
              <FieldContent>
                <Select value={role} onValueChange={(val) => setRole(val ?? "")}>
                  <SelectTrigger className="w-full border-gray-200 bg-white text-gray-700">
                    <SelectValue placeholder="Select one role" />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false} sideOffset={4}>
                    {roles.length === 0 ? (
                      <SelectItem value="Staff">Staff</SelectItem>
                    ) : (
                      roles.map((r) => (
                        <SelectItem key={r.id} value={r.name}>
                          {r.name}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </FieldContent>
            </Field>

            <Field>
              <FieldLabel>
                <FieldTitle>Email</FieldTitle>
              </FieldLabel>
              <FieldContent>
                <div className="relative">
                  <Input 
                    id="email" 
                    type="email" 
                    placeholder="example@gmail.com" 
                    className="border-gray-200 bg-white focus-visible:ring-blue-500" 
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="off"
                  />
                </div>
              </FieldContent>
            </Field>

            <Field>
              <FieldLabel>
                <FieldTitle>Password</FieldTitle>
              </FieldLabel>
              <FieldContent>
                <div className="relative">
                  <Input 
                    id="password" 
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter password" 
                    className="border-gray-200 bg-white focus-visible:ring-blue-500 pr-10" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                  <Button 
                    variant="ghost" 
                    size="icon" 
                    className="absolute right-0 top-0 text-zinc-600 hover:text-zinc-900"
                    onClick={() => setShowPassword(!showPassword)}
                    type="button"
                  >
                    {showPassword ? <RiEyeOffLine className="h-4 w-4" /> : <RiEyeLine className="h-4 w-4" />}
                  </Button>
                </div>
              </FieldContent>
            </Field>
          </div>
        </div>
        
        <div className="p-4 border-t border-gray-200 bg-white flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            className="border-gray-200 bg-white text-zinc-700 hover:bg-zinc-50 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            className="bg-blue-600 text-white hover:bg-blue-700 rounded-lg px-4 h-10 font-medium text-sm transition-colors cursor-pointer shadow-none disabled:opacity-50"
            onClick={handleAddUser}
            disabled={createStaff.isPending}
          >
            {createStaff.isPending ? (
              <RiLoader4Line className="mr-1.5 h-4 w-4 animate-spin shrink-0" />
            ) : (
              <RiAddLine className="mr-1.5 h-4 w-4 shrink-0" />
            )}
            {createStaff.isPending ? "Adding..." : "Add User"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
