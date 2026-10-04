import { useCallback, useEffect, useState } from "react"

export type V2Route =
  | { name: "home" }
  | { name: "plan" }
  | { name: "task"; id: string }
  | { name: "outcome"; id: string }

export function parseRoute(path: string): V2Route {
  const segments = path.replace(/^#/, "").split("/").filter(Boolean)
  if (segments[0] === "plan") return { name: "plan" }
  if (segments[0] === "task" && segments[1]) {
    if (segments[2] === "outcome") return { name: "outcome", id: segments[1] }
    return { name: "task", id: segments[1] }
  }
  return { name: "home" }
}

function currentHash(): string {
  return window.location.hash || "#/"
}

export function useHashRoute() {
  const [hash, setHash] = useState(currentHash)

  useEffect(() => {
    const onHashChange = () => setHash(currentHash())
    window.addEventListener("hashchange", onHashChange)
    return () => window.removeEventListener("hashchange", onHashChange)
  }, [])

  const navigate = useCallback((to: string) => {
    window.location.hash = to
    setHash(to)
  }, [])

  return { hash, route: parseRoute(hash), navigate }
}
