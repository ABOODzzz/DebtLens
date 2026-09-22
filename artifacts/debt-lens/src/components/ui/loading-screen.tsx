import * as React from "react"
import { Loader2 } from "lucide-react"

export function LoadingScreen() {
  return (
    <div className="flex-1 flex items-center justify-center min-h-[50vh]">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-secondary" />
        <p className="text-muted-foreground text-sm animate-pulse">جاري التحميل...</p>
      </div>
    </div>
  )
}
