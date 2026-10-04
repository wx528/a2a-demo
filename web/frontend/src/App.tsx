import { Toaster } from "sonner"
import { useV2Theme } from "@/hooks/useV2Theme"
import { useHashRoute } from "@/lib/router"
import { HomePage } from "@/pages/HomePage"
import { OutcomePage } from "@/pages/OutcomePage"
import { PlanPage } from "@/pages/PlanPage"
import { WorkspacePage } from "@/pages/WorkspacePage"

export default function App() {
  useV2Theme()
  const { route } = useHashRoute()

  let page
  switch (route.name) {
    case "plan":
      page = <PlanPage />
      break
    case "task":
      page = <WorkspacePage id={route.id} />
      break
    case "outcome":
      page = <OutcomePage id={route.id} />
      break
    default:
      page = <HomePage />
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {page}
      <Toaster position="top-center" richColors />
    </div>
  )
}
