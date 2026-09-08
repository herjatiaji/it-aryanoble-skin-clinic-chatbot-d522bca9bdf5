import { RiUserLine } from "@remixicon/react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface ChatFilterProps {
  doctors?: string[];
  value: string;
  onChange: (value: string) => void;
}

export function ChatFilter({ doctors = [], value, onChange }: ChatFilterProps) {
  return (
    <div className="flex items-center gap-3">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="outline"
              className="w-72 justify-start gap-2 bg-white font-normal text-gray-700 hover:bg-gray-50 border-gray-200"
            />
          }
        >
          <RiUserLine className="w-4 h-4 shrink-0 text-gray-500" />
          <span className="truncate">
            {value === "ALL" ? "Filter by doctor" : value}
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
            <DropdownMenuRadioItem closeOnClick value="ALL">
              All Doctors
            </DropdownMenuRadioItem>
            {doctors.map((doctor) => (
              <DropdownMenuRadioItem closeOnClick key={doctor} value={doctor}>
                {doctor}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
