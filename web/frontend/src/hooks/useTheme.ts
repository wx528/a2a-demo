import { useCallback, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"

const STORAGE_KEY = "a2a-theme"

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  document.documentElement.classList.toggle("dark", dark)
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem(STORAGE_KEY) as Theme) || "dark",
  )

  useEffect(() => {
    applyTheme(theme)
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      if (theme === "system") applyTheme("system")
    }
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }, [])

  return { theme, setTheme }
}
