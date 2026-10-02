export interface SseBlock {
  event: string
  data: string
}

export function createSseParser(onBlock: (block: SseBlock) => void) {
  let buf = ""
  return {
    push(chunk: string) {
      buf += chunk
      let idx: number
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        let event = "message"
        const dataLines: string[] = []
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7)
          else if (line.startsWith("data: ")) dataLines.push(line.slice(6))
        }
        if (dataLines.length > 0) onBlock({ event, data: dataLines.join("\n") })
      }
    },
  }
}
