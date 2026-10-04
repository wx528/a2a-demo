import { Moon, Sun } from "lucide-react"
import { useV2Theme } from "@/hooks/useV2Theme"

export function ThemeToggle() {
  const { theme, toggle } = useV2Theme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="切换主题"
      className="flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-panel hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {theme === "dark" ? <Sun className="size-[18px]" aria-hidden /> : <Moon className="size-[18px]" aria-hidden />}
    </button>
  )
}
