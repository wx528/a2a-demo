export const PURPOSES = ["research", "propose", "challenge", "synthesize"] as const

export type PurposeT = (typeof PURPOSES)[number]

export const PURPOSE_LABELS: Record<string, string> = {
  research: "研究",
  propose: "方案",
  challenge: "挑战",
  synthesize: "权衡",
}

export const PURPOSE_DUTIES: Record<string, string> = {
  research: "核实事实与不确定性",
  propose: "提出可执行方案",
  challenge: "检查风险与隐含假设",
  synthesize: "整理权衡与建议",
}

export const PURPOSE_TAG_BY: Record<string, string> = {
  research: "研究",
  propose: "设计",
  challenge: "挑战",
  synthesize: "权衡",
}

export const DEFAULT_ASSIGNMENTS: Record<string, string> = {
  research: "ada",
  propose: "turing",
  challenge: "linus",
  synthesize: "sage",
}
