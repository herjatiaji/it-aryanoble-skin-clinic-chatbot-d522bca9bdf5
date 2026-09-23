"use client";

import { useMemo, useState } from "react";
import {
  RiUserLine,
  RiMedicineBottleLine,
  RiCalendarLine,
  RiCloseLine,
  RiArrowDownSLine,
  RiSearchLine,
  RiCheckLine,
} from "@remixicon/react";
import { format } from "date-fns";
import type { DateRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ChatTypeOption {
  value: string;
  label: string;
}

interface ChatFilterProps {
  users?: string[];
  userFilter: string;
  onUserChange: (value: string) => void;

  chatTypes?: ChatTypeOption[];
  chatTypeFilter: string;
  onChatTypeChange: (value: string) => void;

  dateRange?: DateRange;
  onDateRangeChange: (range: DateRange | undefined) => void;
}

export function ChatFilter({
  users = [],
  userFilter,
  onUserChange,
  chatTypes = [],
  chatTypeFilter,
  onChatTypeChange,
  dateRange,
  onDateRangeChange,
}: ChatFilterProps) {
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [isUserPopoverOpen, setIsUserPopoverOpen] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState("");

  const filteredUsers = useMemo(() => {
    if (!userSearchQuery.trim()) return users;
    const q = userSearchQuery.toLowerCase().trim();
    return users.filter((u) => u.toLowerCase().includes(q));
  }, [users, userSearchQuery]);

  const formattedDateRange = dateRange?.from
    ? dateRange.to
      ? dateRange.from.getFullYear() === dateRange.to.getFullYear()
        ? `${format(dateRange.from, "d MMM")} - ${format(dateRange.to, "d MMM yyyy")}`
        : `${format(dateRange.from, "d MMM yy")} - ${format(dateRange.to, "d MMM yy")}`
      : format(dateRange.from, "d MMM yyyy")
    : null;

  const selectedChatTypeLabel =
    chatTypeFilter === "ALL"
      ? "Filter by type"
      : chatTypes.find((t) => t.value === chatTypeFilter)?.label || chatTypeFilter;

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* 1. Filter by User / Doctor with Search */}
      <Popover open={isUserPopoverOpen} onOpenChange={setIsUserPopoverOpen}>
        <PopoverTrigger
          render={
            <Button
              variant="outline"
              title={userFilter === "ALL" ? "Filter by user" : userFilter}
              className="h-10 w-56 justify-between gap-2 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 text-sm rounded-lg shadow-none cursor-pointer"
            />
          }
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <RiUserLine className="w-4 h-4 shrink-0 text-zinc-500" />
            <span className="truncate text-left">
              {userFilter === "ALL" ? "Filter by user" : userFilter}
            </span>
          </div>
          <RiArrowDownSLine className="w-4 h-4 shrink-0 text-zinc-400 ml-1" />
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="w-56 p-2 flex flex-col gap-2 z-50 bg-white border border-gray-200 shadow-none rounded-lg ring-0 outline-none"
        >
          {/* Search Bar inside Popover */}
          <div className="relative w-full">
            <RiSearchLine className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-zinc-400 pointer-events-none" />
            <Input
              placeholder="Search user..."
              value={userSearchQuery}
              onChange={(e) => setUserSearchQuery(e.target.value)}
              className="h-8 pl-8 pr-7 text-xs bg-zinc-50 border-gray-200 focus-visible:ring-blue-500 rounded-md"
              autoFocus
            />
            {userSearchQuery && (
              <button
                type="button"
                onClick={() => setUserSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 cursor-pointer"
              >
                <RiCloseLine className="size-3.5" />
              </button>
            )}
          </div>

          {/* User List */}
          <div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto overscroll-contain pr-0.5">
            {(!userSearchQuery || "all users".includes(userSearchQuery.toLowerCase().trim())) && (
              <button
                type="button"
                onClick={() => {
                  onUserChange("ALL");
                  setIsUserPopoverOpen(false);
                  setUserSearchQuery("");
                }}
                className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
                  userFilter === "ALL"
                    ? "bg-blue-50 text-blue-700"
                    : "text-zinc-700 hover:bg-zinc-100"
                }`}
              >
                <span className="truncate">All Users</span>
                {userFilter === "ALL" && <RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />}
              </button>
            )}

            {filteredUsers.map((user) => {
              const isSelected = userFilter === user;
              return (
                <button
                  type="button"
                  key={user}
                  title={user}
                  onClick={() => {
                    onUserChange(user);
                    setIsUserPopoverOpen(false);
                    setUserSearchQuery("");
                  }}
                  className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-medium text-left transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-blue-50 text-blue-700"
                      : "text-zinc-700 hover:bg-zinc-100"
                  }`}
                >
                  <span className="truncate min-w-0 flex-1">{user}</span>
                  {isSelected && <RiCheckLine className="size-3.5 text-blue-600 shrink-0 ml-1.5" />}
                </button>
              );
            })}

            {filteredUsers.length === 0 &&
              userSearchQuery &&
              !"all users".includes(userSearchQuery.toLowerCase().trim()) && (
                <div className="py-4 text-center text-xs text-zinc-400">
                  No users found
                </div>
              )}
          </div>
        </PopoverContent>
      </Popover>

      {/* 2. Filter by Chat / Doctor Type */}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="outline"
              title={selectedChatTypeLabel}
              className="h-10 w-56 justify-between gap-2 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 text-sm rounded-lg shadow-none cursor-pointer"
            />
          }
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <RiMedicineBottleLine className="w-4 h-4 shrink-0 text-zinc-500" />
            <span className="truncate text-left">{selectedChatTypeLabel}</span>
          </div>
          <RiArrowDownSLine className="w-4 h-4 shrink-0 text-zinc-400 ml-1" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56 max-h-64 overflow-y-auto bg-white border border-gray-200 shadow-none rounded-lg ring-0 outline-none">
          <DropdownMenuRadioGroup value={chatTypeFilter} onValueChange={onChatTypeChange}>
            <DropdownMenuRadioItem closeOnClick value="ALL">
              All Chat Types
            </DropdownMenuRadioItem>
            {chatTypes.map((type) => (
              <DropdownMenuRadioItem closeOnClick key={type.value} value={type.value} title={type.label}>
                <span className="truncate">{type.label}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 3. Filter by Date Range */}
      <Popover open={isCalendarOpen} onOpenChange={setIsCalendarOpen}>
        <PopoverTrigger
          render={
            <Button
              variant="outline"
              title={formattedDateRange || "Filter by date range"}
              className="h-10 w-64 justify-between gap-2 bg-white font-normal text-zinc-700 hover:bg-zinc-50 border-gray-200 text-sm rounded-lg shadow-none cursor-pointer"
            />
          }
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <RiCalendarLine className="w-4 h-4 shrink-0 text-zinc-500" />
            <span className="truncate text-left">
              {formattedDateRange || "Filter by date range"}
            </span>
          </div>
          {formattedDateRange ? (
            <span
              role="button"
              tabIndex={0}
              className="p-0.5 hover:bg-gray-100 rounded text-gray-400 hover:text-gray-600 shrink-0 cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                onDateRangeChange(undefined);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  onDateRangeChange(undefined);
                }
              }}
            >
              <RiCloseLine className="w-4 h-4" />
            </span>
          ) : (
            <RiArrowDownSLine className="w-4 h-4 shrink-0 text-zinc-400" />
          )}
        </PopoverTrigger>
        <PopoverContent align="end" className="w-auto min-w-70 p-2 bg-white border border-gray-200 shadow-none rounded-lg ring-0 outline-none">
          <Calendar
            mode="range"
            selected={dateRange}
            onSelect={(range) => {
              onDateRangeChange(range);
            }}
            numberOfMonths={1}
            autoFocus
          />
          {formattedDateRange && (
            <div className="p-2 border-t border-gray-100 flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs text-gray-500 hover:text-gray-900 shadow-none focus-visible:ring-0"
                onClick={() => {
                  onDateRangeChange(undefined);
                  setIsCalendarOpen(false);
                }}
              >
                Reset Date Filter
              </Button>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}


