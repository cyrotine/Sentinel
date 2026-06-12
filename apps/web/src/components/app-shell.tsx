"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { Hexagon, LayoutDashboard, Settings, PlayCircle, GitBranch, FolderGit2 } from "lucide-react"

const navItems = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Repositories", href: "/repositories", icon: FolderGit2 },
  { label: "Agent", href: "/agents", icon: GitBranch },
  { label: "Past Repositories", href: "/demo-mode", icon: PlayCircle },
  { label: "Settings", href: "/settings", icon: Settings },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex h-screen overflow-hidden bg-neutral-950 text-neutral-50 selection:bg-neutral-800">
      <aside className="flex w-64 flex-col border-r border-neutral-900 bg-neutral-950">
        <div className="flex h-16 items-center px-6 border-b border-transparent">
          <Hexagon className="h-5 w-5 text-neutral-100 mr-3" />
          <span className="text-sm font-semibold tracking-wide text-neutral-100">Forge</span>
        </div>
        
        <div className="px-4 py-4">
          <p className="px-2 text-[10px] font-medium tracking-wider text-neutral-500 uppercase mb-3">
            Workspace
          </p>
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => {
              const isActive = pathname === item.href || (pathname.startsWith(item.href) && item.href !== "/")
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive 
                      ? "bg-neutral-900 text-neutral-50" 
                      : "text-neutral-400 hover:bg-neutral-900/50 hover:text-neutral-200"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                  {isActive && (
                    <div className="ml-auto h-1.5 w-1.5 rounded-full bg-neutral-400" />
                  )}
                </Link>
              )
            })}
          </nav>
        </div>

        <div className="mt-auto border-t border-neutral-900 p-4">
          <div className="flex items-center gap-3 px-2">
            <div className="h-8 w-8 rounded-full bg-neutral-800 flex items-center justify-center text-xs font-medium border border-neutral-700">
              JD
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-medium text-neutral-200">Jordan Diaz</span>
              <span className="text-xs text-neutral-500 flex items-center gap-1">
                <GitBranch className="h-3 w-3" /> acme
              </span>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden bg-[#0A0A0A]">
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
