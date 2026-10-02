import { useCallback, useState } from "react"
import { ChatInput } from "@/components/ChatInput"
import { CreateMeetingDialog } from "@/components/CreateMeetingDialog"
import { HomeEmptyState } from "@/components/HomeEmptyState"
import { MessageList } from "@/components/MessageList"
import { ParticipantBar } from "@/components/ParticipantBar"
import { RoomHeader } from "@/components/RoomHeader"
import { Sidebar } from "@/components/Sidebar"
import { TurnControlBar } from "@/components/TurnControlBar"
import { useMeetings } from "@/hooks/useMeetings"
import { useMeetingRoom } from "@/hooks/useMeetingRoom"
import type { Meeting } from "@/types"

function updateUrl(meetingId: string | null) {
  const url = new URL(window.location.href)
  if (meetingId) url.searchParams.set("meeting", meetingId)
  else url.searchParams.delete("meeting")
  window.history.replaceState({}, "", url)
}

export default function App() {
  const [meetingId, setMeetingId] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("meeting"),
  )
  const [createOpen, setCreateOpen] = useState(false)
  const { meetings, refresh, remove } = useMeetings()
  const room = useMeetingRoom(meetingId)

  const openMeeting = useCallback((id: string) => {
    setMeetingId(id)
    updateUrl(id)
  }, [])

  const closeMeeting = useCallback(() => {
    setMeetingId(null)
    updateUrl(null)
  }, [])

  const handleCreated = useCallback(
    (meeting: Meeting) => {
      setCreateOpen(false)
      void refresh()
      openMeeting(meeting.id)
    },
    [refresh, openMeeting],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      const ok = await remove(id)
      if (ok && id === meetingId) closeMeeting()
    },
    [remove, meetingId, closeMeeting],
  )

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        meetings={meetings}
        activeId={meetingId}
        onOpen={openMeeting}
        onCreate={() => setCreateOpen(true)}
        onDelete={(id) => void handleDelete(id)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        {!meetingId ? (
          <HomeEmptyState onCreate={() => setCreateOpen(true)} />
        ) : (
          <>
            <RoomHeader meeting={room.meeting} connected={room.connected} onClose={closeMeeting} />
            {room.meeting && <ParticipantBar participants={room.meeting.participants} />}
            <TurnControlBar
              turnInfo={room.turnInfo}
              turnRunning={room.turnRunning}
              autoPlay={room.autoPlay}
              onToggleAutoPlay={room.setAutoPlay}
              onContinue={() => void room.runNextTurn()}
            />
            {room.meeting ? (
              <MessageList meeting={room.meeting} />
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                正在加载会议室…
              </div>
            )}
            <ChatInput onSend={room.sendMessage} />
          </>
        )}
      </div>
      <CreateMeetingDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />
    </div>
  )
}
