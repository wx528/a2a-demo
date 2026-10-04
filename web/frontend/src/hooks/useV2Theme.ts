import { useCallback, useState } from "react"

export type V2Theme = "light" | "dark"

const STORAGE_KEY = "v2-theme"

function readInitialTheme(): V2Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "light" || stored === "dark") return stored
  } catch {
    return "light"
  }
  return "light"
}

export function useV2Theme() {
  const [theme, setTheme] = useState<V2Theme>(() => {
    const initial = readInitialTheme()
    document.documentElement.classList.toggle("dark", initial === "dark")
    return initial
  })

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: V2Theme = prev === "light" ? "dark" : "light"
      document.documentElement.classList.toggle("dark", next === "dark")
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        return next
      }
      return next
    })
  }, [])

  return { theme, toggle }
}
