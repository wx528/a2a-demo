export interface RoleMetaT {
  emoji: string
  zh: string
  en: string
}

export const ROLES: Record<string, RoleMetaT> = {
  ada: { emoji: "🧬", zh: "研究员", en: "Ada" },
  turing: { emoji: "🧠", zh: "方案设计师", en: "Turing" },
  linus: { emoji: "⚡", zh: "挑战者", en: "Linus" },
  sage: { emoji: "⚖️", zh: "决策助手", en: "Sage" },
  user: { emoji: "👤", zh: "你", en: "You" },
  system: { emoji: "⚙️", zh: "系统", en: "System" },
}

export const STAGE_ORDER = ["clarify", "compare", "review", "recommend"] as const

export const STAGE_LABELS: Record<string, string> = {
  clarify: "澄清需求",
  compare: "比较方案",
  review: "评审风险",
  recommend: "形成建议",
}

export function roleMeta(author: string): RoleMetaT {
  return ROLES[author] ?? { emoji: "⚙️", zh: author, en: author }
}

export function roleLabel(author: string): string {
  const meta = roleMeta(author)
  return `${meta.zh} · ${meta.en}`
}
